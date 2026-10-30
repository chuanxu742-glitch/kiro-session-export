"""Build the distributable single-file Kiro session exporter."""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = ('sections', 'options', 'preferences', 'exporting', 'cli')


def build_source(project_root=ROOT):
    """Return a deterministic standalone script from trusted repository sources."""
    project_root = Path(project_root)
    module_sources = []
    for name in MODULES:
        module_path = project_root / 'kiro_export' / f'{name}.py'
        source = module_path.read_text(encoding='utf-8')
        module_sources.append((name, source))
    entry_source = (project_root / 'kiro-md.py').read_text(encoding='utf-8')

    lines = [
        '#!/usr/bin/env python3',
        '"""Standalone build of Kiro Session & Conversation Export."""',
        'import sys as _standalone_sys',
        'import types as _standalone_types',
        '_standalone_package = _standalone_types.ModuleType("kiro_export")',
        '_standalone_package.__path__ = []',
        '_standalone_package.__package__ = "kiro_export"',
        '_standalone_sys.modules["kiro_export"] = _standalone_package',
    ]
    for name, source in module_sources:
        module_name = f'kiro_export.{name}'
        lines.extend([
            f'_standalone_module = _standalone_types.ModuleType({module_name!r})',
            f'_standalone_module.__package__ = "kiro_export"',
            f'_standalone_sys.modules[{module_name!r}] = _standalone_module',
            f'setattr(_standalone_package, {name!r}, _standalone_module)',
            f'exec(compile({source!r}, {("<" + module_name + ">")!r}, "exec"), '
            '_standalone_module.__dict__)',
        ])
    lines.extend([
        '# The original entry point runs in this script\'s normal __main__ globals.',
        'exec(compile(' + repr(entry_source) + ', "<kiro-md.py>", "exec"), globals())',
        '',
    ])
    return '\n'.join(lines)


def build_standalone(output_path=None, project_root=ROOT):
    """Write the built script to output_path, creating parent directories."""
    project_root = Path(project_root)
    if output_path is None:
        output_path = project_root / 'dist' / 'kiro-md.py'
    else:
        output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', encoding='utf-8', newline='\n') as output_file:
        output_file.write(build_source(project_root))
    return output_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='write the standalone script to this path')
    args = parser.parse_args(argv)
    output = build_standalone(args.output)
    print(f'Built standalone script: {output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
