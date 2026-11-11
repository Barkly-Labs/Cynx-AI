from pathlib import Path

from ai.chat_engine import ChatEngine
from ai.mode_manager import ModeManager
from tools.filesystem import FilesystemTool
from tools.tool_router import ToolRouter


def test_filesystem_tool_accepts_repo_relative_paths_from_any_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = FilesystemTool().call({'path': 'README.md'})

    assert result.success is True
    assert 'CYN-X' in result.output

    outside_file = tmp_path / 'outside.txt'
    outside_file.write_text('secret', encoding='utf-8')
    denied = FilesystemTool().call({'path': str(outside_file)})
    assert denied.success is False
    assert 'Access denied' in denied.output


def test_filesystem_tool_accepts_absolute_project_paths(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)

    result = FilesystemTool().call({'path': str(repo_root / 'tools' / 'filesystem.py')})

    assert result.success is True
    assert 'class FilesystemTool' in result.output


def test_filesystem_tool_does_not_create_files_from_extra_arguments(monkeypatch, tmp_path):
    monkeypatch.setattr('tools.filesystem.ALLOWED_ROOT', tmp_path)
    target = tmp_path / 'read-only.txt'

    result = FilesystemTool().call({
        'path': target.name,
        'mode': 'w',
        'content': 'must not be written',
    })

    assert result.success is False
    assert 'read-only' in result.output
    assert target.exists() is False


def test_filesystem_tool_schema_and_router_dispatch():
    router = ToolRouter()
    router.register_tool(FilesystemTool())

    schema = router.as_ollama_tools()[0]['function']
    assert schema['name'] == 'filesystem'
    assert schema['parameters']['required'] == ['path']
    assert schema['parameters']['properties']['path']['type'] == 'string'

    result = router.call_tool('filesystem', {'path': 'README.md'})
    assert result.success is True
    assert 'CYN-X' in result.output


def test_filesystem_tool_is_exposed_only_in_permitted_modes():
    router = ToolRouter()
    router.register_tool(FilesystemTool())
    engine = ChatEngine(None, None, None, router, ModeManager())

    normal_tools = {
        spec['function']['name'] for spec in engine._ollama_tools(mode='normal')
    }
    helper_tools = {
        spec['function']['name'] for spec in engine._ollama_tools(mode='helper')
    }
    solver_tools = {
        spec['function']['name'] for spec in engine._ollama_tools(mode='solver')
    }

    assert 'filesystem' in normal_tools
    assert 'filesystem' in helper_tools
    assert 'filesystem' not in solver_tools
