<div align="center">
  <img src="banner.png" alt="Kiro Session Export Preview" width="100%" style="max-width: 800px; border-radius: 12px; margin-bottom: 20px;">
</div>

# Kiro Session & Conversation Export

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.x](https://img.shields.io/badge/python-3.x-blue.svg)](https://www.python.org/)
[![Tests](https://github.com/chuanxu742-glitch/kiro-session-export/actions/workflows/tests.yml/badge.svg)](https://github.com/chuanxu742-glitch/kiro-session-export/actions/workflows/tests.yml)

Terminal-native Markdown and JSON export for **Kiro IDE** and **Kiro CLI** sessions.

This is a public fork of [MeXenon/kiro-session-export](https://github.com/MeXenon/kiro-session-export).
It adds modern IDE storage support, referenced full tool outputs and linked
sub-agent streams, structured JSON export, saved preferences, command-line
export, and modular development with standalone builds. The original project's
history and Apache 2.0 license are preserved. Release notes below describe
upstream releases; build this fork to use the additions described here.

`kiro-md.py` lets you browse local Kiro conversations, filter exactly which
sections to keep, and export Markdown or structured JSON files for review, debugging,
handoff, audits, or feeding another model.

---

## What It Solves

Kiro sessions can be difficult to review outside the app:

- Kiro IDE stores session shell files and execution records in separate places.
- Kiro CLI stores a compact `.json` index plus a detailed `.jsonl` event stream.
- Tool calls, file edits, shell commands, MCP calls, web activity, reasoning, and
  compaction summaries are not convenient to read manually.
- Long sessions can contain huge terminal outputs or file reads that need
  trimming before they are useful in another context window.

This tool reads those local storage formats and exports the selected content
as readable Markdown or structured JSON, with interactive controls.

---

## Highlights

- **Kiro IDE and Kiro CLI support:** choose the source at startup.
- **Full Kiro CLI JSONL parsing:** exports real prompts, assistant messages,
  reasoning, file reads, file creates, file edits, terminal commands, terminal
  outputs, grep/glob/code searches, MCP calls, sub-agent/task calls, web search,
  web fetch, errors, events, and compaction summaries.
- **IDE execution-record joining:** maps Kiro IDE shell histories to execution
  records so tool activity appears in the right Markdown sections.
- **Session ID finder:** search both IDE and CLI stores in parallel by full
  session ID or prefix. If a match exists on both sides, the tool asks which one
  to export.
- **Visible session IDs:** each session row shows its session ID. The ID
  shortens to a searchable prefix only when the terminal is too narrow for
  the title. The directory picker shows the session count, age, short name,
  and path.
- **Workspace-aware browsing:** sessions are grouped by workspace/project
  directory. Running from inside a workspace auto-selects that workspace.
- **CLI helper-session toggle:** Kiro CLI can create many subagent/helper
  sessions. They are hidden by default and can be shown with `e`.
- **Selectable export destination:** save to file, clipboard, or both.
- **Selectable format:** Markdown (`.md`) or UTF-8 JSON (`.json`), for single
  sessions, separate files, combined exports, and the clipboard.
- **Untruncated output by default:** the output cap starts at **ALL** and
  Agent Reasoning starts enabled. Sections can still be toggled individually.
- **Save-location prompt:** when writing files, choose the project directory or
  the script directory. If both are the same, no prompt is shown.
- **Multi-session export:** export selected sessions separately or merge them
  into one combined Markdown file.
- **Chain merge export for IDE:** export detected compaction chains as one
  unified document with lineage annotations.
- **Interactive section filter:** toggle every section, apply presets, and cap
  large outputs before writing. The footer shows lines and an approximate
  token count for the current selection.
- **Orchestration filter:** a Kiro CLI crew stays in the transcript where the
  lead agent launched it. The default keeps each stage's last report. Status,
  commands, command output, file activity, and reasoning are separate rows
  with their own line and token counts.
- **Live-context mode for IDE:** reproduce Kiro IDE's compaction behavior by
  keeping only the active context after summarization.
- **Zero required dependencies:** uses Python standard library by default.
  Optional `orjson` speeds up large JSON parsing.

---

## Quick Start

### Run from the source checkout

Clone the repository, then run the source entry point with Python 3.9 or newer:

```bash
git clone https://github.com/chuanxu742-glitch/kiro-session-export.git
cd kiro-session-export
python kiro-md.py
```

The source entry point uses the repository's `kiro_export` package. On systems
where `python` selects Python 2, use `python3` instead.

### Build and copy one standalone file

The standard-library builder packages the repository modules into one Python
script. Run it from a checkout:

```bash
python tools/build_standalone.py
```

It writes `dist/kiro-md.py`. Copy that file to another location and run it with
Python 3.9 or newer; it does not need the checkout or additional Python packages.
Use `--output` to choose another destination:

```bash
python tools/build_standalone.py --output /path/to/kiro-md.py
```

For faster parsing on very large sessions, install optional `orjson` in the
Python environment used to run the script. The exporter falls back to the
standard-library `json` module when `orjson` is unavailable.

---

## Command-Line Use

The interactive menu remains available when run without arguments in a terminal.
When standard input is piped, use `list` or `export`; the program prints a hint
and exits instead of waiting for keyboard input.

```bash
python kiro-md.py
```

List sessions as JSON or export selected sessions from the command line:

```bash
python kiro-md.py list --source ide --json
python kiro-md.py list --source all --json --workspace ./my-project
python kiro-md.py export --source ide --session SESSION_ID --format markdown --output ./exports
python kiro-md.py export --source cli --session ID_ONE --session ID_TWO --format json --output ./exports --preset full
```

`list` accepts `--source ide|cli|all`, `--json`, and optional `--workspace DIR`
(to filter to a workspace path).
`export` accepts `--source ide|cli`, one or more `--session ID` values,
`--format json|markdown`, `--output DIR`, and `--preset default|chat|full`.
Turn scope options are `--last N`, `--first N`, `--turns START:END`, or
`--live`. `--output-cap N` limits long outputs; `--clean-chat` removes Kiro
context noise from chat; `--combine` merges selected sessions; and `--reuse`
reuses saved interactive settings. Interactive choices and the last source are
remembered; the first source defaults to IDE. Press `R` in the source menu to
reuse those settings, then choose the session to export. Session IDs are not
saved. In an IDE or CLI session list, press `U` to toggle **Reuse saved export
settings**; the `OPTIONS` display shows whether it is on or off.

## Development

The `kiro_export` package separates shared export settings (`options.py`),
interactive preference storage (`preferences.py`), terminal and JSON/Markdown
rendering (`exporting.py`), and command-line parsing (`cli.py`). `sections.py`
provides the shared section and preset definitions. `kiro-md.py` remains the
source entry point; `tools/build_standalone.py` embeds these trusted package
sources into the standalone script.

Run the standard-library test suite and build the standalone file with:

```bash
python -m unittest discover -v
python tools/build_standalone.py
```

## Running From Any Workspace

You can run the script by absolute path from any project directory. This lets the
tool detect the workspace you are currently inside:

```powershell
python "C:\path\to\kiro-md.py"
```

No project path is hardcoded in the tool. It uses your current working directory
and Kiro's local storage paths.

---

## Startup Menu

At launch, choose the data source:

```text
[1] Kiro IDE sessions
[2] Kiro CLI sessions
[3] Find by session ID
```

### Kiro IDE Sessions

Automatically scans both modern IDE sessions (`session.json` plus
`messages.jsonl`) and legacy workspace indexes/execution records. Modern
sessions support workspace browsing, ID lookup, turn selection, section
filtering, and Markdown export. If both stores contain the same session ID,
the modern copy takes precedence. Legacy compaction chains still support
chain view and merged export.

### Kiro CLI Sessions

Scans Kiro CLI session files. CLI mode uses `.json` files for metadata and
prefers the matching `.jsonl` event stream for the actual transcript. This is
what makes file edits, terminal output, MCP calls, subagent calls, and
compactions appear correctly.

### Find By Session ID

Searches Kiro IDE and Kiro CLI stores in parallel. You can paste a full session
ID or a useful prefix. Exact matches win. If a prefix matches multiple sessions,
the tool lists them and asks which one to use.

---

## Interface Flow

1. **Choose source:** IDE, CLI, or Find by session ID.
2. **Browse workspaces:** workspaces are sorted by recent activity. The current
   workspace is highlighted when detected.
3. **Select sessions:** type IDs like `1`, `1, 3`, or `a` for all listed.
4. **Choose turns:** full session, the first or last N turns, a turn range, or
   live context. Every choice shows its turn count, lines, and estimated tokens.
5. **Filter sections:** use the fullscreen filter UI to choose what to export.
6. **Choose format:** Markdown (`M`, default) or JSON (`J`).
7. **Choose destination:** file, clipboard, or both.
8. **Choose save folder:** project directory or script directory when they differ.

Useful browsing keys:

| Key | Action |
|-----|--------|
| `w` | Switch workspace/directory |
| `w1`, `w2`, ... | Jump directly to a workspace from the summary |
| `x` | Clear workspace filter and show all workspaces |
| `m` | Show more rows |
| `s` | Toggle sort mode |
| `r` | Reload session index |
| `e` | CLI only: show/hide helper/subagent sessions |
| `U` | Toggle reuse of saved export settings; `OPTIONS` shows on/off |
| `c` | IDE only: toggle chain-grouped view |
| `ce <id>` | IDE only: export an entire detected chain |
| `q` | Quit |

---

## Export Destinations

Press `Q` in the section filter to continue. Choose the export format:

```text
[M] Markdown (.md) [Default]
[J] JSON (.json)
```

Then choose where the exported content goes:

```text
[F] File
[C] Clipboard
[B] Both
```

When writing files, the tool asks where to save:

```text
[P] Project directory
[S] Script directory
```

If the project directory and script directory are the same, the question is
skipped. For separate exports across multiple workspaces, `Project directories`
saves each session next to its own project.

JSON exports are valid documents with a `sessions` array, including for a
single session. Separate JSON filenames include the session ID so sessions
with the same title cannot overwrite each other. Copying multiple sessions
produces one JSON document rather than concatenated JSON fragments.
All file exports preserve existing files: a repeated filename is saved with
`_2`, `_3`, and so on. This also protects combined exports, chain exports,
and Markdown files. The save message shows the actual filename.

### JSON Structure

JSON exports use the tool's normalized events, not a byte-for-byte dump of
Kiro's internal storage. A simplified example:

```json
{
  "format": "kiro-session-export",
  "schema_version": 1,
  "options": {"output_line_cap": 0},
  "sessions": [{
    "id": "example-session",
    "title": "Example conversation",
    "source": "Kiro IDE",
    "events": [{
      "type": "terminal_cmd",
      "tool": "execute_pwsh",
      "tool_call_id": "example-call",
      "arguments": {"command": "Write-Output hello"}
    }, {
      "type": "terminal_output",
      "tool_call_id": "example-call",
      "output": "hello",
      "success": true
    }]
  }]
}
```

Modern IDE events retain their recorded timestamps, message IDs, tool-call
IDs, exact tool input arguments, and tool results. Reasoning uses the
`reasoning` event type. Legacy IDE and CLI exports contain the fields their
parsers make available. Images remain short notes, without binary/base64 data.
Session identity, workspace, model information, and source metadata are
included when **Session Metadata** is selected.
This also includes context usage percentage, autonomy mode, session type,
parent session IDs, continuation count, and compaction information when
available. Modern IDE metadata retains the recorded workspace/root paths,
creation and modification timestamps, model, mode, and schema versions.

Every session also contains `export_info`, even when **Session Metadata**
is off, so a selected excerpt cannot be mistaken for the whole transcript:

- `scope`: the requested `full`, `first`, `last`, `range`, or `live` selection,
  with the requested turn count or range where applicable.
- `source_turn_count` and `selected_turn_count`: turn counts before and after
  the scope selection, before section filtering and message limits.
- `source_event_count`, `selected_event_count`, and `exported_event_count`:
  parsed event counts before scope selection, after scope selection, and in
  the final JSON. Parsed events are not raw JSONL records; the parser can
  split or summarize a record.
- `excluded_sections`: event categories present in the selected scope that
  were disabled by the section filter. Message caps and clean-chat may omit
  more events; their settings remain in the document's `options`.
- `read_error_count`: detected IDE message-stream read/parse errors before
  scope selection, including linked child streams and external output files,
  even when the **Errors** section is disabled. This
  counts detected errors, not missing messages; zero does not prove a
  complete source. Enable **Errors** and export the full session to see the
  available error details.
- `sub_execution_count`: linked child streams present in the selected export.
- `external_output_files`: distinct referenced output files loaded or failed
  in the selected export, including its linked child streams.
- `limitations`: `normalized_events_not_raw_backup` and `image_data_omitted`.
  If child files cannot be linked to any recorded invocation, the export
  additionally declares `unlinked_sub_executions_not_included`. These describe
  format limitations, rather than claiming that every session contains an image.

Metadata statistics such as executions, credits, context usage, and compaction
counts describe the parsed source session; `export_info` describes the selected
excerpt. Session Metadata remains optional and its private fields are omitted
when disabled. The existing version 1 fields remain; these fields are additive.

JSON follows the selected turns, enabled sections, message limits, and clean-chat
option. `output_line_cap: 0` means **ALL**. If you choose a finite output cap,
output bodies are truncated; recorded tool input arguments remain exact.
For modern IDE tool results, Kiro's full-output notices and `<file name="...">`
wrappers are resolved against this session's `tool-outputs` directory. The
complete UTF-8 file replaces the shortened `output`; JSON retains the original
notice as `recorded_output` and the relative filename/status in `external_outputs`.
Both output fields follow the output cap. Missing, unreadable, or out-of-session
files leave the recorded notice available and produce a read error.

Modern IDE sub-agent records retain `sub_session_id` and their parent execution
ID. A child's `sub-executions/<id>.jsonl` is included as `sub_execution.events`
on its completion record, or its invocation if no completion was recorded.
Markdown shows the child stream in a collapsible details block. Child streams
keep their own record order rather than being interleaved into the parent.
They follow the **Sub-Agent Calls** toggle and the parent's selected turns;
the same section, clean-chat, and output settings apply inside each stream.
Message limits apply independently per stream. Repeated or cyclic references
are linked without duplicating the same child stream.
Nested line/token estimates include child content before its section/message
filtering, so they can overestimate selected content; actual JSON and Markdown
sizes can differ.
CLI orchestration exports include only enabled stage layers.
The filter's line/token estimates use Markdown rendering; JSON size differs
because it retains structured fields and tool arguments.

---

## Supported Sections

| Section | Default | Description |
|---------|---------|-------------|
| User Messages | On | User prompts and requests |
| Agent Messages | On | Assistant responses |
| Agent Reasoning | On | Thinking/reasoning traces when present in local data |
| File Reads | Off | Files inspected by the agent |
| File Creates | On | New files created by the agent |
| File Edits | On | File modifications |
| File Deletes | On | Deleted files |
| Terminal Commands | On | Shell commands requested by the agent |
| Terminal Outputs | On | Shell command results |
| Process Control | On | Process/background-control activity |
| Code Search | Off | Grep/glob/code lookup activity |
| Diagnostics | Off | IDE diagnostics when available |
| Web Searches | Off | Web search queries and result links |
| Web Fetches | Off | Retrieved URL content |
| MCP Calls | Off | MCP tool calls and responses |
| Sub-Agent Calls | On | Single sub-agent invocations and results |
| Orchestrations | On | CLI crews, in place, with each stage's last report |
| Compaction Summary | On | Context compaction summaries |
| Intent Classification | Off | Intent classification records |
| Errors | Off | Error records |
| Clarifying Q&A | Off | Agent clarification prompts |
| Session Events | On | Lifecycle and bookkeeping events |
| Session Metadata | On | Session ID, workspace, model, context, credits, etc. |

---

## Filter Presets And Caps

The filter screen lets you:

- Toggle each section on or off.
- Load presets such as chat-only, chat plus terminal, code activity, outputs
  only, or full export.
- Cap large output blocks to a fixed number of lines, or keep **ALL** (default).
- Keep only the last N user messages, agent messages, reasoning blocks, or
  summaries.
- Enable clean-chat mode to strip IDE context noise from user prompts.
- Under Orchestrations, choose completed, cancelled, error, or still-running
  crews, and turn stage layers on or off. Each row shows how many lines and
  approximately how many tokens that choice adds. For every output cap the
  filter offers, a heavy layer's count matches the fenced text that will be
  written. The default layers are the stage roster and the last report.
  Commands, command output, file contents, and reasoning stay off until you
  enable them.
- The output cap also trims stage command output, file dumps, searches, and
  reasoning when those layers are on. It does not trim the last-state reports.

This is useful when a raw session is too large for a context window. A crew
with dozens of stages can hold tens of megabytes of command output. The filter
shows that cost before anything is written. The default export keeps the
report each stage actually returned, including a report recovered from a
stage whose crew was cancelled or failed.

---

## Storage Layouts

### Kiro IDE

Modern Kiro IDE storage (including Kiro 1.4.51):

```text
~/.kiro/sessions/
└── <workspace-hash>/<session-id>/
    ├── session.json
    └── messages.jsonl
```

The message stream contains `{id, timestamp, payload}` records. The exporter
reads user/assistant messages, reasoning, compaction summaries, tool calls and
results, sub-agent reports, interactions, errors, and usage. Calls and results
keep their recorded order. Sub-agent start/completion reports and linked
`sub-executions` streams are retained, with each child stream attached to its
corresponding parent call.
Image attachments become short notes rather than
base64 dumps. Exports contain the content stored in the stream and referenced
session-local `tool-outputs` files; omitted file contents are not reconstructed
from the current working tree.
Missing streams or malformed records produce a warning before export; enable
the **Errors** section to include the details in Markdown.

Override the modern session root in PowerShell:

```powershell
$env:KIRO_IDE_SESSIONS_DIR = "D:\custom\sessions"
python .\kiro-md.py
```

The override points to the directory containing the workspace-hash folders.
No override is needed for the default location. The CLI source remains separate.

Legacy Kiro IDE storage:

```text
%APPDATA%/Kiro/User/globalStorage/kiro.kiroagent/
├── workspace-sessions/<workspace-id>/
│   ├── sessions.json
│   └── <sessionId>.json
└── <workspace-hash>/<bucket>/<execution-record>
```

Override the IDE root with:

```bash
KIRO_HOME=/custom/path python kiro-md.py
```

`KIRO_HOME` overrides the legacy `kiro.kiroagent` root. It is not the modern
session-root setting. Both layouts are read in place; the tool does not move
or modify Kiro data.

### Kiro CLI

Typical Kiro CLI storage:

```text
~/.kiro/sessions/cli/
├── <sessionId>.json
├── <sessionId>.jsonl
├── <sessionId>.history
└── <sessionId>.lock
```

The `.json` file is compact metadata. The `.jsonl` file is the detailed event
stream used for rich exports.

Override the CLI session directory with:

```bash
KIRO_CLI_SESSIONS_DIR=/custom/path python kiro-md.py
```

---

## Privacy And GitHub Safety

The repository does not need your project paths or user directory to work.

- No local workspace path is hardcoded.
- No personal home directory is required in the README.
- The script discovers storage from environment variables and platform defaults.
- Exported Markdown files are generated locally and are not committed by the
  tool.

Before publishing, you can scan for accidental local paths:

```bash
rg -n "C:\\\\Users|/Users/|/home/|Desktop[\\\\/]work|\\.kiro[\\\\/]sessions" .
```

Expected matches should only be generic examples or platform storage references.

---

## Release Notes

### [v1.4.0](https://github.com/MeXenon/kiro-session-export/releases/tag/v1.4.0)

- After a session loads, choose the full session, the first or last N turns,
  a turn range, or the live context. Each choice shows turns, lines, and
  estimated tokens.
- A screenshot returned by a file read stays an image note, so the turn size
  follows the conversation.

### [v1.3.0](https://github.com/MeXenon/kiro-session-export/releases/tag/v1.3.0)

- CLI orchestrations export where the lead agent launched them, with each
  stage's last report by default.
- The section filter counts lines and tokens for orchestration status and
  stage layers, in fixed columns, with orchestration choices marked as
  sub-options.
- IDE startup reads execution metadata from the ends of the record instead
  of the whole transcript.

### [v1.2.1](https://github.com/MeXenon/kiro-session-export/releases/tag/v1.2.1)

- Added full session IDs beneath every IDE and CLI session row.
- Added each workspace's latest full session ID to the workspace picker.
- Renamed the numeric selection column from `ID` to `#` to avoid ambiguity.

### [v1.2.0](https://github.com/MeXenon/kiro-session-export/releases/tag/v1.2.0)

- Added Kiro CLI session browsing.
- Added detailed Kiro CLI `.jsonl` event-stream parsing.
- Added startup source chooser for IDE, CLI, and session-ID search.
- Added parallel session-ID lookup across IDE and CLI stores.
- Added CLI helper/subagent session toggle.
- Added workspace highlighting and current-workspace auto-selection.
- Added CLI message-count column and real transcript-size display.
- Added save-location selection between project directory and script directory.
- Added multi-workspace save behavior for separate exports.
- Updated CLI exports to include file reads, creates, edits, terminal commands,
  terminal outputs, MCP calls, web activity, subagent/task calls, compactions,
  and errors.

### v1.1.x

- Added richer Kiro IDE chain detection and chain merge export.
- Added interactive filtering, section presets, output caps, and clean-chat mode.
- Added faster execution-record indexing for Kiro IDE storage.

---

## Compatibility

Tested storage families:

- Kiro IDE local desktop storage
- Modern Kiro IDE `session.json` / `messages.jsonl` storage
- Kiro CLI local session storage with `.json` plus `.jsonl`

Supported operating systems:

- Windows
- macOS
- Linux

The script is read-only against Kiro storage. It writes the Markdown/JSON exports
you choose and stores validated exporter preferences separately from Kiro data.

Run the synthetic format/compatibility tests with Python's standard library:

```bash
python -m unittest -v test_session_formats
```

---

## Related Projects

Looking for the same idea for OpenAI Codex sessions? Search for
`codex-session-export`.

---

## License

Apache 2.0. See [LICENSE](LICENSE).
