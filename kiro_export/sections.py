"""Shared event categories, presets and orchestration choices."""
from typing import Dict

SECTION_DEFS = [
    ('user_message',     'User Messages',       '👤', True ),
    ('agent_message',    'Agent Messages',      '🤖', True ),
    ('reasoning',        'Agent Reasoning',     '🧠', True ),
    ('file_read',        'File Reads',          '📖', False),
    ('file_create',      'File Creates',        '🆕', True ),
    ('file_edit',        'File Edits',          '✏️ ', True ),
    ('file_delete',      'File Deletes',        '🗑️ ', True ),
    ('terminal_cmd',     'Terminal Commands',   '💻', True ),
    ('terminal_output',  'Terminal Outputs',    '📤', True ),
    ('process_ctrl',     'Process Control',     '⚙️ ', True ),
    ('code_search',      'Code Search',         '🔎', False),
    ('diagnostics',      'Diagnostics',         '🩺', False),
    ('web_search',       'Web Searches',        '🌐', False),
    ('web_fetch',        'Web Fetches',         '🔗', False),
    ('mcp_tool',         'MCP Calls',           '🔌', False),
    ('sub_agent',        'Sub-Agent Calls',     '🧩', True ),
    ('orchestration',    'Orchestrations',      '🎭', True ),
    ('summarization',    'Compaction Summary',  '✂️ ', True ),
    ('intent',           'Intent Classification','🎯', False),
    ('error',            'Errors',              '❗', False),
    ('user_input',       'Clarifying Q&A',      '❓', False),
    ('session_event',    'Session Events',      '🔔', True ),
    ('session_meta',     'Session Metadata',    '📝', True ),
]

ALL_SECTION_KEYS = {s[0] for s in SECTION_DEFS}

ACTION_TYPE_TO_SECTION: Dict[str, str] = {
    'say':                'agent_message',
    'reasoning':          'reasoning',
    'readFile':           'file_read',
    'readFiles':          'file_read',
    'readCode':           'file_read',
    'read_file':          'file_read',
    'create':             'file_create',
    'write':              'file_create',
    'replace':            'file_edit',
    'append':             'file_edit',
    'str_replace':        'file_edit',
    'delete':             'file_delete',
    'runCommand':         'terminal_cmd',
    'execute_pwsh':       'terminal_cmd',
    'controlProcess':     'process_ctrl',
    'getProcessOutput':   'process_ctrl',
    'search':             'code_search',
    'file_search':        'code_search',
    'getDiagnostics':     'diagnostics',
    'remote_web_search':  'web_search',
    'webFetch':           'web_fetch',
    'mcp':                'mcp_tool',
    'invokeSubAgent':     'sub_agent',
    'subagent_response':  'sub_agent',
    'subagentResponse':   'sub_agent',
    'specAgent':          'sub_agent',
    'summarization':      'summarization',
    'intentClassification':'intent',
    'displayError':       'error',
    'userInput':          'user_input',
    'analyzeRequirements':'sub_agent',
    'model':              None,   # internal book-keeping — drop
}

FILTER_PRESETS = [
    ('Defaults',        None, False),
    ('Chat Only',       {'user_message','agent_message','session_meta','session_event'}, False),
    ('Chat + Reasoning',{'user_message','agent_message','reasoning','session_meta','session_event'}, False),
    ('Chat + Terminal', {'user_message','agent_message','terminal_cmd','terminal_output',
                          'process_ctrl','session_meta','session_event'}, False),
    ('Code Activity',   {'user_message','agent_message','file_read','file_create','file_edit',
                          'file_delete','terminal_cmd','terminal_output','session_meta','session_event'}, False),
    ('Outputs Only',    {'terminal_output'}, False),
    ('Full Export',     ALL_SECTION_KEYS, False),
]

ORCH_STATUSES = (
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
    ('error', 'Error'),
    ('running', 'Still running'),
)

ORCH_LAYERS = (
    ('last_state', 'Last state', True),
    ('roster', 'Stage roster', True),
    ('brief', 'Stage briefs', False),
    ('shared_task', 'Shared task', False),
    ('talk', 'Stage messages', False),
    ('commands', 'Stage commands', False),
    ('command_output', 'Stage command output', False),
    ('reasoning', 'Stage reasoning', False),
    ('file_read', 'Stage file reads', False),
    ('file_write', 'Stage file writes', False),
    ('search', 'Stage searches', False),
)

ORCH_HEAVY_LAYERS = ('command_output', 'reasoning', 'file_read', 'file_write', 'search')

DEFAULT_OUTPUT_CAP = 0

CAP_STEPS = [0, 1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30, 50, 100, 200, 500]
