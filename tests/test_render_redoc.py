import json
import sys
from pathlib import Path

import pytest

from docs import render_redoc

TEMPLATE = "<title>{{TITLE}}</title>"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory holding a spec and a template, as the docs workflow's checkout does."""
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "openapi.json").write_text(json.dumps({"info": {"title": "<A & B>"}}), encoding="utf-8")
    (root / "redoc.html.template").write_text(TEMPLATE, encoding="utf-8")
    monkeypatch.chdir(root)
    return root


def render(monkeypatch: pytest.MonkeyPatch, spec: str, template: str, output: str) -> None:
    monkeypatch.setattr(sys, "argv", ["render_redoc.py", "--spec", spec, "--template", template, "--output", output])
    render_redoc.main()


def test_renders_escaped_title(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    render(monkeypatch, "openapi.json", "redoc.html.template", "site/index.html")

    assert (workspace / "site" / "index.html").read_text(encoding="utf-8") == "<title>&lt;A &amp; B&gt;</title>"


def test_falls_back_to_default_title(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (workspace / "openapi.json").write_text(json.dumps({"info": {"title": " "}}), encoding="utf-8")

    render(monkeypatch, "openapi.json", "redoc.html.template", "index.html")

    assert (workspace / "index.html").read_text(encoding="utf-8") == "<title>API Documentation</title>"


@pytest.mark.parametrize(
    ("spec", "template", "output"),
    [
        ("../openapi.json", "redoc.html.template", "index.html"),
        ("openapi.json", "/etc/hostname", "index.html"),
        ("openapi.json", "redoc.html.template", "../index.html"),
    ],
)
def test_refuses_paths_outside_the_working_directory(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, spec: str, template: str, output: str
) -> None:
    (workspace.parent / "openapi.json").write_text("{}", encoding="utf-8")

    with pytest.raises(SystemExit, match="outside the working directory"):
        render(monkeypatch, spec, template, output)

    assert not (workspace.parent / "index.html").exists()


def test_refuses_symlink_out_of_the_working_directory(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (workspace / "site").symlink_to(workspace.parent, target_is_directory=True)

    with pytest.raises(SystemExit, match="outside the working directory"):
        render(monkeypatch, "openapi.json", "redoc.html.template", "site/index.html")

    assert not (workspace.parent / "index.html").exists()


def test_refuses_empty_spec(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (workspace / "openapi.json").write_text("", encoding="utf-8")

    with pytest.raises(SystemExit, match="empty"):
        render(monkeypatch, "openapi.json", "redoc.html.template", "index.html")


def test_refuses_template_without_placeholder(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (workspace / "redoc.html.template").write_text("<title></title>", encoding="utf-8")

    with pytest.raises(SystemExit, match="placeholder"):
        render(monkeypatch, "openapi.json", "redoc.html.template", "index.html")
