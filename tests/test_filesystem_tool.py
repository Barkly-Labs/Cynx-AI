from pathlib import Path

from tools.filesystem import FilesystemTool


def test_filesystem_tool_accepts_repo_relative_paths_from_any_cwd(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
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
