"""
Filesystem tool with safe, limited operations. This is intentionally conservative.
"""
from typing import Dict
from pathlib import Path
from tools.base import BaseTool, ToolResult

ALLOWED_ROOT = Path(__file__).resolve().parent.parent


class FilesystemTool(BaseTool):
    name = 'filesystem'
    description = 'Read files within an allowed directory (read-only).'

    def schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "List directories or read text files within the project "
                    "root. Read-only; paths outside the project root are denied."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Path relative to the repository root, or an "
                                "absolute path within it. For the repository's "
                                "tools directory, use 'tools' (not 'project/tools')."
                            )
                        }
                    },
                    "required": ["path"]
                }
            }
        }

    def _resolve_target(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = ALLOWED_ROOT / candidate
        return candidate.resolve()

    def _read_text(self, path: Path) -> str:
        for encoding in ('utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be', 'latin-1'):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        return path.read_text(encoding='utf-8', errors='replace')

    def call(self, args: Dict) -> ToolResult:
        unsupported_arguments = set(args) - {'path'}
        if unsupported_arguments:
            return ToolResult(
                False,
                'Filesystem tool is read-only and accepts only a path.'
            )
        path = args.get('path')
        if not path:
            return ToolResult(False, 'No path provided')
        try:
            target = self._resolve_target(path)
            try:
                target.relative_to(ALLOWED_ROOT)
            except ValueError:
                return ToolResult(False, 'Access denied to that path')
            if not target.exists():
                return ToolResult(False, 'Path does not exist')
            if target.is_dir():
                return ToolResult(True, '\n'.join([p.name for p in target.iterdir()]))
            return ToolResult(True, self._read_text(target))
        except Exception as e:
            return ToolResult(False, f'Filesystem error: {e}')
