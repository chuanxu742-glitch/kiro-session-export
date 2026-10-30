"""Export option value object shared by CLI and renderers."""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, Tuple


@dataclass
class ExportOptions:
    """Rendering options with an adapter for the historical eight-item tuple."""

    sections: dict
    clean_content: bool = False
    output_cap: int = 0
    user_cap: int = 0
    agent_cap: int = 0
    reasoning_cap: int = 0
    summary_cap: int = 0
    orch_filter: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.sections, dict):
            raise TypeError('sections must be a dict')
        if not isinstance(self.orch_filter, dict):
            raise TypeError('orch_filter must be a dict')
        self.sections = deepcopy(self.sections)
        self.orch_filter = deepcopy(self.orch_filter)
        if not isinstance(self.clean_content, bool):
            raise TypeError('clean_content must be a bool')
        for name in ('output_cap', 'user_cap', 'agent_cap', 'reasoning_cap', 'summary_cap'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f'{name} must be a non-negative integer')

    @classmethod
    def from_legacy(cls, value: Any) -> 'ExportOptions':
        if isinstance(value, cls):
            return cls(*value.legacy_tuple())
        if not isinstance(value, (tuple, list)) or len(value) != 8:
            raise ValueError('legacy export options must contain exactly eight values')
        return cls(*value)

    def legacy_tuple(self) -> Tuple[Any, ...]:
        return (deepcopy(self.sections), self.clean_content, self.output_cap,
                self.user_cap, self.agent_cap, self.reasoning_cap,
                self.summary_cap, deepcopy(self.orch_filter))

    def __iter__(self) -> Iterator[Any]:
        return iter(self.legacy_tuple())

    def __getitem__(self, index):
        return self.legacy_tuple()[index]

    def render_kwargs(self) -> Dict[str, Any]:
        sections, clean, output, user, agent, reasoning, summary, orch = self.legacy_tuple()
        return {'section_filter': sections, 'clean_content': clean,
                'output_cap': output, 'user_cap': user, 'agent_cap': agent,
                'reasoning_cap': reasoning, 'summary_cap': summary,
                'orch_filter': orch}

    def as_dict(self) -> Dict[str, Any]:
        return {'sections': deepcopy(self.sections),
                'clean_content': self.clean_content,
                'output_cap': self.output_cap, 'user_cap': self.user_cap,
                'agent_cap': self.agent_cap, 'reasoning_cap': self.reasoning_cap,
                'summary_cap': self.summary_cap,
                'orch_filter': deepcopy(self.orch_filter)}

    @classmethod
    def from_dict(cls, value: Any) -> 'ExportOptions':
        if not isinstance(value, dict):
            raise TypeError('export options must be a dict')
        clean = value.get('clean_content', False)
        if not isinstance(clean, bool):
            clean = False
        caps = {}
        for name in ('output_cap', 'user_cap', 'agent_cap', 'reasoning_cap', 'summary_cap'):
            cap = value.get(name, 0)
            caps[name] = cap if isinstance(cap, int) and not isinstance(cap, bool) and cap >= 0 else 0
        sections = value.get('sections', {})
        if not isinstance(sections, dict):
            sections = {}
        orch = value.get('orch_filter', {})
        if not isinstance(orch, dict):
            orch = {}
        return cls(sections=sections, clean_content=clean, orch_filter=orch, **caps)
