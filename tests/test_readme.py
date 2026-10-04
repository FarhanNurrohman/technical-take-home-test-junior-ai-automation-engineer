"""Documentation contract tests for the project README."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_contains_required_sections() -> None:
    content = _readme().casefold()
    required = (
        "panduan instalasi dan pengujian",
        "logika algoritma matching",
        "pemanfaatan ai coding assistant",
    )
    assert all(title in content for title in required)


def test_readme_references_existing_prompts_and_python_files() -> None:
    content = _readme()
    for prompt_path in re.findall(r"\.github/prompts/[A-Za-z0-9_.-]+", content):
        assert (ROOT / prompt_path).is_file(), prompt_path
    for command in re.findall(r"python\s+([A-Za-z0-9_.-]+\.py)", content):
        assert (ROOT / command).is_file(), command


def test_readme_environment_variables_match_example() -> None:
    content = _readme()
    example_names = {
        line.split("=", 1)[0].strip()
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }
    readme_names = set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", content))
    documented = readme_names & example_names
    assert documented == example_names


def test_readme_does_not_contain_secrets_or_cursor() -> None:
    content = _readme()
    assert "Cursor" not in content
    assert not re.search(r"AIza|private_key|BEGIN PRIVATE KEY", content, re.IGNORECASE)


def test_readme_mermaid_blocks_use_known_syntax() -> None:
    content = _readme()
    blocks = re.findall(r"```mermaid\s*\n(.*?)```", content, re.DOTALL)
    assert blocks
    assert all(re.match(r"\s*(flowchart|graph|sequenceDiagram|stateDiagram|classDiagram)\b", block) for block in blocks)
