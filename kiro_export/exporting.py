"""Pure rendering and serialization helpers for normalized session events."""

import copy
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Any

from .options import ExportOptions
from .sections import ALL_SECTION_KEYS, ORCH_HEAVY_LAYERS, ORCH_LAYERS, ORCH_STATUSES, SECTION_DEFS


@dataclass
class RenderContext:
    """Callbacks supplied by the application for runtime-specific rendering."""

    guess_lang: Callable
    strip_ide_context: Callable
    load_orchestration_heavy: Callable
    render_orchestration: Callable
    json_orchestration: Callable


def default_orch_filter() -> Dict:
    return {'statuses': {key: True for key, _label in ORCH_STATUSES},
            'layers': {key: on for key, _label, on in ORCH_LAYERS},
            'latest_only': False}


def cap_text(text: str, cap: int) -> str:
    """Keep the last ``cap`` lines; non-positive caps preserve all lines."""
    if not text or cap <= 0:
        return text or ''
    lines = text.split('\n')
    if len(lines) <= cap:
        return text
    kept = lines[-cap:]
    return f"... ({len(lines) - cap} lines trimmed) ...\n" + '\n'.join(kept)


def select_items(data: List[Dict], options: ExportOptions) -> List[Dict]:
    """Apply section and per-event tail caps while preserving transcript order."""
    caps = {'user_message': options.user_cap, 'agent_message': options.agent_cap,
            'reasoning': options.reasoning_cap, 'summarization': options.summary_cap}
    counters = {key: 0 for key in caps}
    selected = []
    for item in reversed(data):
        kind = item['type']
        if not options.sections.get(kind, False):
            continue
        if kind in caps and caps[kind] > 0:
            counters[kind] += 1
            if counters[kind] > caps[kind]:
                continue
        selected.append(item)
    selected.reverse()
    return selected


def _json_value(value):
    """Convert parser containers to JSON values without mutating the transcript."""
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, set):
        return [_json_value(item) for item in sorted(value, key=str)]
    if isinstance(value, Path):
        return str(value)
    return value


def _nested_events(data: List[Dict]) -> Iterable[Dict]:
    for item in data:
        yield item
        child = item.get('sub_execution')
        if child:
            yield from _nested_events(child.get('events') or [])


def _session_read_error_count(data: List[Dict]) -> int:
    return sum(item.get('type') == 'error' and item.get('kind') == 'session_read'
               for item in _nested_events(data))


def _auxiliary_export_counts(events: List[Dict]) -> Dict:
    children, loaded, failed = set(), set(), set()
    for item in _nested_events(events):
        child = item.get('sub_execution')
        if child and child.get('status') == 'loaded':
            children.add(child['id'])
        for output in item.get('external_outputs') or []:
            (loaded if output['status'] == 'loaded' else failed).add(output['file'])
    return {'sub_execution_count': len(children),
            'external_output_files': {'loaded': len(loaded), 'failed': len(failed)}}


def _json_export_info(parser, sections: Dict, events: List[Dict]) -> Dict:
    """Describe selection, source counts and known limitations."""
    limitations = ['normalized_events_not_raw_backup', 'image_data_omitted']
    if getattr(parser, 'unlinked_sub_execution_count', 0):
        limitations.append('unlinked_sub_executions_not_included')
    return {
        'scope': _json_value(getattr(parser, 'extraction_scope',
                                     {'mode': 'full', 'label': 'full session'})),
        'source_turn_count': getattr(parser, 'source_turn_count', parser.get_turn_count()),
        'selected_turn_count': parser.get_turn_count(),
        'source_event_count': getattr(parser, 'source_event_count', len(parser.data)),
        'selected_event_count': len(parser.data),
        'exported_event_count': len(events),
        'excluded_sections': sorted({item['type'] for item in parser.data
                                     if not sections.get(item['type'], False)}),
        'read_error_count': getattr(parser, 'source_read_error_count',
                                    _session_read_error_count(parser.data)),
        'limitations': limitations,
        **_auxiliary_export_counts(events),
    }


def _select_json_events(data: List[Dict], options: ExportOptions,
                        context: RenderContext) -> List[Dict]:
    events = []
    last_message = None
    orch = options.orch_filter
    for item in select_items(data, options):
        selected = (context.json_orchestration(item, orch, options.output_cap)
                    if item['type'] == 'orchestration'
                    else {key: value for key, value in item.items() if key != 'sub_execution'})
        event = _json_value(selected)
        kind = event['type']
        if options.clean_content and kind in ('user_message', 'agent_message'):
            if kind == 'user_message':
                event['content'] = context.strip_ide_context(event.get('content') or '')
            key = (kind, event.get('content'))
            if not event.get('content', '').strip() or key == last_message:
                continue
            last_message = key
        for key in ('output', 'modified_content', 'response', 'recorded_output'):
            if isinstance(event.get(key), str):
                event[key] = cap_text(event[key], options.output_cap)
        if kind == 'web_fetch' and isinstance(event.get('content'), str):
            event['content'] = cap_text(event['content'], options.output_cap)
        child = item.get('sub_execution')
        if child:
            nested = _select_json_events(child['events'], options, context)
            event['sub_execution'] = {
                'id': child['id'], 'status': child['status'], 'events': nested,
                'source_event_count': len(child['events']), 'exported_event_count': len(nested),
                'read_error_count': _session_read_error_count(child['events']),
            }
        events.append(event)
    return events


def serialize_sessions_json(parsers, options: ExportOptions,
                            context: RenderContext) -> str:
    """Serialize normalized selected events in the established versioned schema."""
    sections = options.sections
    orch = options.orch_filter
    sessions = []
    for parser in parsers:
        events = _select_json_events(parser.data, options, context)
        session = {'title': parser.title, 'source': parser.metadata.get('source') or 'Kiro IDE',
                   'export_info': _json_export_info(parser, sections, events), 'events': events}
        if sections.get('session_meta', False):
            session.update(id=parser.session_id, workspace=parser.workspace_dir,
                           created_ms=parser.date_created, models=sorted(parser.model_titles),
                           user_turn_count=parser.get_turn_count(), execution_count=parser.execution_count,
                           credits_used=parser.credits_used, context_usage_pct=parser.context_usage_pct,
                           autonomy_mode=parser.autonomy_mode, session_type=parser.session_type,
                           parent_session_ids=list(parser.parent_session_ids),
                           continuation_count=parser.continuation_count,
                           compaction_count=parser.compaction_count,
                           started_from_compaction=parser.started_from_compaction,
                           metadata=_json_value(parser.metadata))
        sessions.append(session)
    document = {'format': 'kiro-session-export', 'schema_version': 1,
                'options': {'sections': sections, 'output_line_cap': options.output_cap,
                            'message_caps': {'user_message': options.user_cap,
                                             'agent_message': options.agent_cap,
                                             'reasoning': options.reasoning_cap,
                                             'summarization': options.summary_cap},
                            'clean_content': options.clean_content, 'orchestration': orch},
                'sessions': sessions}
    return json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def render_markdown(parser, options: ExportOptions, context: RenderContext) -> str:
    """Render one parser using the established Markdown layout."""
    section_filter = options.sections
    clean_content = options.clean_content
    output_cap = options.output_cap
    user_cap = options.user_cap
    agent_cap = options.agent_cap
    reasoning_cap = options.reasoning_cap
    summary_cap = options.summary_cap
    orch_filter = options.orch_filter
    if section_filter is None:
        section_filter = {s[0]: True for s in SECTION_DEFS}
    if orch_filter is None:
        orch_filter = default_orch_filter()

    def _cap_text(text: str, cap: int = 0) -> str:
        c = cap if cap > 0 else output_cap
        return cap_text(text, c)

    md: List[str] = []

    # Header — title and compaction badges
    badge_bits = []
    if parser.started_from_compaction:
        badge_bits.append('↻ from compaction')
    if parser.compaction_count:
        badge_bits.append(f'✂ compacted ×{parser.compaction_count}')
    if parser.continuation_count:
        badge_bits.append(f'↪ continued ×{parser.continuation_count}')
    if parser.hidden:
        badge_bits.append('hidden')
    badges = '  '.join(badge_bits)
    title_line = f"# {parser.title}"
    if badges:
        title_line += f"   _({badges})_"
    md.append(title_line + '\n')

    if section_filter.get('session_meta', False):
        md.append('```yaml')
        md.append(f"Session ID:   {parser.session_id}")
        md.append(f"Workspace:    {parser.workspace_dir or '?'}")
        if parser.date_created:
            try:
                dt = datetime.fromtimestamp(parser.date_created / 1000.0).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                dt = str(parser.date_created)
            md.append(f"Created:      {dt}")
        if parser.model_titles:
            md.append(f"Model(s):     {', '.join(sorted(parser.model_titles))}")
        if parser.autonomy_mode:
            md.append(f"Autonomy:     {parser.autonomy_mode}")
        if parser.session_type:
            md.append(f"Session type: {parser.session_type}")
        md.append(f"Executions:   {parser.execution_count}")
        md.append(f"User turns:   {parser.user_turn_count}")
        if parser.context_usage_pct:
            md.append(f"Context:      {parser.context_usage_pct:.1f}%")
        if parser.credits_used:
            md.append(f"Credits:      {parser.credits_used:.4f}")
        if parser.parent_session_ids:
            md.append(f"Parents:      {len(parser.parent_session_ids)} ancestor session(s)")
        md.append('```\n')

    last_rendered_msg = None
    for item in select_items(parser.data, options):
        t = item['type']
        if not section_filter.get(t, False):
            continue

        if item.get('result_only'):
            state = ' (failed)' if item.get('state') == 'Failed' else ''
            md.append(f"**Result — `{item.get('tool', 'unknown')}`{state}:**\n")
            output = item.get('output') or ''
            if output.strip():
                md.append(f"```text\n{_cap_text(output)}\n```\n")

        elif t == 'user_message':
            content = item.get('content', '')
            if clean_content:
                content = context.strip_ide_context(content)
                if not content.strip():
                    continue
                key = ('user', content)
                if key == last_rendered_msg:
                    continue
                last_rendered_msg = key
            md.append(f"## 👤 User\n\n{content}\n")

        elif t == 'agent_message':
            content = item.get('content', '').strip()
            if not content:
                continue
            if clean_content:
                key = ('agent', content)
                if key == last_rendered_msg:
                    continue
                last_rendered_msg = key
            md.append(f"## 🤖 Agent\n\n{content}\n")

        elif t == 'reasoning':
            content = item.get('content', '').strip()
            if not content:
                continue
            md.append(f"> 🧠 **Reasoning**\n>\n> " + content.replace('\n', '\n> ') + "\n")

        elif t == 'summarization':
            content = item.get('content', '').strip()
            if not content:
                continue
            where = item.get('where', 'inline')
            heading = '## ✂️ Compaction Summary (intro)' if where == 'intro' else '## ✂️ Compaction Summary'
            md.append(f"{heading}\n\n{content}\n")

        elif t == 'file_read':
            files = item.get('files') or []
            err = item.get('error')
            tool = item.get('tool', 'readFile')
            state = item.get('state', '')
            if files:
                bullets = []
                for f in files:
                    line = f.get('path', '?')
                    if f.get('start') is not None and f.get('end') is not None:
                        line += f"  [{f['start']}–{f['end']}]"
                    bullets.append(f"- `{line}`")
                head = f"### 📖 Read ({tool})"
                if err:
                    head += f"  *— failed: {err.splitlines()[0][:80]}*"
                md.append(head + "\n\n" + "\n".join(bullets) + "\n")
            out = item.get('output', '')
            if isinstance(out, str) and out.strip():
                out = _cap_text(out)
                md.append(f"```text\n{out}\n```\n")

        elif t == 'file_create':
            path = item.get('path', '?')
            content = item.get('modified_content') or ''
            why = item.get('explanation') or ''
            state = item.get('state', '')
            err = item.get('error')
            head = f"### 🆕 Create `{path}`"
            if err:
                head += f"  *— failed: {err.splitlines()[0][:80]}*"
            if state and state not in ('Accepted', 'Success'):
                head += f"  *— {state}*"
            md.append(head)
            if why:
                md.append(f"\n> {why}\n")
            if isinstance(content, str) and content:
                lang = context.guess_lang(path)
                md.append(f"\n```{lang}\n{_cap_text(content)}\n```\n")

        elif t == 'file_edit':
            path = item.get('path', '?')
            why = item.get('explanation') or ''
            state = item.get('state', '')
            tool = item.get('tool', 'edit')
            orig = item.get('original_content') or ''
            modf = item.get('modified_content') or ''
            err = item.get('error')
            head = f"### ✏️ Edit `{path}`  *(via {tool})*"
            if err:
                head += f"  *— failed: {err.splitlines()[0][:80]}*"
            if state and state not in ('Accepted', 'Success'):
                head += f"  *— {state}*"
            md.append(head)
            if why:
                md.append(f"\n> {why}\n")
            # Render a compact diff when both sides exist
            if isinstance(modf, str) and modf:
                lang = context.guess_lang(path)
                md.append(f"\n**Modified:**\n\n```{lang}\n{_cap_text(modf)}\n```\n")
            elif isinstance(orig, str) and orig:
                md.append(f"\n_(modified content omitted)_\n")

        elif t == 'file_delete':
            path = item.get('path', '?')
            why = item.get('explanation') or ''
            state = item.get('state', '')
            err = item.get('error')
            head = f"### 🗑️ Delete `{path}`"
            if err:
                head += f"  *— failed: {err.splitlines()[0][:80]}*"
            elif state and state not in ('Accepted', 'Success'):
                head += f"  *— {state}*"
            md.append(head + ("\n\n> " + why + "\n" if why else "\n"))

        elif t == 'terminal_cmd':
            cmd = item.get('command', '')
            cwd = item.get('cwd', '')
            why = item.get('explanation', '')
            tool = item.get('tool', 'runCommand')
            state = item.get('state', '')
            err = item.get('error')
            head = f"### 💻 {tool}"
            if state and state not in ('Accepted', 'Success'):
                head += f"  *({state})*"
            if err:
                head += f"  *— failed: {err.splitlines()[0][:80]}*"
            md.append(head)
            if why:
                md.append(f"\n> {why}")
            if cwd:
                md.append(f"\n> `cwd: {cwd}`")
            md.append(f"\n```powershell\n{cmd}\n```\n" if (os.name == 'nt') else f"\n```bash\n{cmd}\n```\n")

        elif t == 'terminal_output':
            out = item.get('output', '')
            ec = item.get('exit_code')
            if not isinstance(out, str):
                out = json.dumps(out, ensure_ascii=False, indent=2)
            trimmed = _cap_text(out)
            head = "**Output:**"
            if ec is not None:
                head += f"  *(exit {ec})*"
            if trimmed.strip():
                md.append(f"{head}\n\n```text\n{trimmed}\n```\n")

        elif t == 'process_ctrl':
            tool = item.get('tool', '?')
            summary = item.get('summary', '')
            cmd = item.get('command', '')
            out = item.get('output', '')
            err = item.get('error')
            head = f"### ⚙️ Process — `{tool}` {summary}"
            if err:
                head += f"  *— failed: {err.splitlines()[0][:80]}*"
            md.append(head)
            if cmd:
                md.append(f"\n```text\n{cmd}\n```")
            if isinstance(out, str) and out.strip():
                md.append(f"\n**Output:**\n\n```text\n{_cap_text(out)}\n```")
            md.append('')

        elif t == 'code_search':
            q = item.get('query', '')
            why = item.get('why', '')
            out = item.get('output', '')
            err = item.get('error')
            head = f"### 🔎 Search: `{q}`"
            if err:
                head += f"  *— failed: {err.splitlines()[0][:80]}*"
            md.append(head)
            if why:
                md.append(f"\n> {why}")
            if isinstance(out, str) and out.strip():
                md.append(f"\n```text\n{_cap_text(out)}\n```")
            md.append('')

        elif t == 'diagnostics':
            paths = item.get('paths') or []
            ic = item.get('issue_count', 0)
            md.append(f"> 🩺 **Diagnostics:** {len(paths)} file(s), {ic} issue(s)\n")

        elif t == 'web_search':
            q = item.get('query', '')
            results = item.get('results') or []
            md.append(f"### 🌐 Web Search: `{q}`")
            bullets = []
            for r in results[:10]:
                if isinstance(r, dict):
                    bullets.append(f"- [{r.get('title','(no title)')}]({r.get('url','')})")
            if bullets:
                md.append('\n' + '\n'.join(bullets))
            md.append('')

        elif t == 'web_fetch':
            url = item.get('url', '')
            content = item.get('content', '')
            md.append(f"### 🔗 Web Fetch: <{url}>")
            if isinstance(content, str) and content.strip():
                md.append(f"\n```text\n{_cap_text(content)}\n```")
            md.append('')

        elif t == 'mcp_tool':
            server = item.get('server', '?')
            tool = item.get('tool_name', '?')
            args = item.get('arguments') or {}
            resp = item.get('response', '')
            md.append(f"### 🔌 MCP: `{server}::{tool}`")
            if args:
                md.append(f"\n```json\n{json.dumps(args, indent=2, ensure_ascii=False)}\n```")
            if isinstance(resp, str) and resp.strip():
                md.append(f"\n**Response:**\n\n```text\n{_cap_text(resp)}\n```")
            md.append('')

        elif t == 'orchestration':
            heavy = None
            if any((orch_filter.get('layers') or {}).get(key) for key in ORCH_HEAVY_LAYERS):
                heavy = context.load_orchestration_heavy(item, orch_filter, output_cap)
            block = context.render_orchestration(item, orch_filter, output_cap, heavy)
            if block.strip():
                md.append(block)

        elif t == 'sub_agent':
            kind = item.get('kind', '')
            if kind == 'invoke':
                name = item.get('name', '')
                expl = item.get('explanation', '')
                prompt = item.get('prompt', '')
                md.append(f"### 🧩 Sub-Agent → `{name}`")
                if expl:
                    md.append(f"\n> {expl}")
                if prompt:
                    md.append(f"\n```text\n{_cap_text(prompt)}\n```")
                md.append('')
            elif kind == 'response':
                resp = item.get('response', '')
                md.append(f"### 🧩 Sub-Agent Response\n\n{resp}\n")
            elif kind == 'spec':
                md.append(f"> 🧩 **Spec Agent** invoked\n")
            else:
                md.append(f"### 🧩 Sub-Agent: `{kind}`\n")
            child = item.get('sub_execution')
            if child and child.get('events'):
                view = copy.copy(parser)
                view.data = child['events']
                view.title = f"Sub-execution {child['id']}"
                view.started_from_compaction = False
                view.continuation_count = 0
                view.compaction_count = sum(event['type'] == 'summarization' for event in view.data)
                view.hidden = False
                nested_sections = dict(section_filter, session_meta=False)
                body = view.to_markdown(
                    section_filter=nested_sections, clean_content=clean_content,
                    output_cap=output_cap, user_cap=user_cap, agent_cap=agent_cap,
                    reasoning_cap=reasoning_cap, summary_cap=summary_cap, orch_filter=orch_filter)
                md.append(f"<details>\n<summary>Sub-execution `{child['id']}`</summary>\n\n{body}\n</details>\n")

        elif t == 'intent':
            cls = item.get('classification', '?')
            md.append(f"> 🎯 **Intent:** {cls}\n")

        elif t == 'error':
            msg = item.get('message', '')
            k   = item.get('kind', '')
            md.append(f"> ❗ **Error** ({k}): {msg}\n")

        elif t == 'user_input':
            qs = item.get('questions') or []
            for q in qs:
                if isinstance(q, dict):
                    question = q.get('question', '')
                    ans = (q.get('response') or {}).get('answer') if isinstance(q.get('response'), dict) else ''
                    md.append(f"> ❓ **Q:** {question}\n>\n> **A:** {ans}\n")

        elif t == 'session_event':
            md.append(f"> 🔔 **{item.get('content', item.get('event', ''))}**\n")

    return "\n".join(md)
