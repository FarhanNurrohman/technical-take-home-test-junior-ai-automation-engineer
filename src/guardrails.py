"""Input and output guardrails for the finance chatbot."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


_BLOCKED = re.compile(
    r"(?:data|transaksi)\s+mentah|seluruh\s+data|nomor\s+jurnal|kredensial|api.?key|password",
    re.IGNORECASE,
)
_RUPIAH = re.compile(r"-?\s*Rp\s*[0-9]+(?:[.,][0-9]+)*", re.IGNORECASE)


@dataclass(frozen=True)
class QuestionGuardResult:
    """Result of validating a user question."""

    blocked: bool
    question: str
    message: str = ""


@dataclass(frozen=True)
class ResponseGuardResult:
    """Detected unverifiable amounts in a model response."""

    foreign_amounts: list[str] = field(default_factory=list)
    missing_keys: list[str] = field(default_factory=list)


def guard_question(question: str, max_length: int = 500) -> QuestionGuardResult:
    """Block raw-data and credential requests before they reach the model."""
    normalized = str(question or "").strip()[:max_length]
    if not normalized:
        return QuestionGuardResult(True, "", "Masukkan pertanyaan tentang hasil settlement.")
    if _BLOCKED.search(normalized):
        return QuestionGuardResult(
            True,
            normalized,
            "Saya tidak dapat menampilkan data mentah, nomor jurnal, atau kredensial.",
        )
    return QuestionGuardResult(False, normalized)


def _allowed_amounts(tool_results: list[Any]) -> set[str]:
    allowed: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)
        elif isinstance(value, str):
            allowed.update(match.group(0).replace(" ", "") for match in _RUPIAH.finditer(value))

    visit(tool_results)
    return allowed


def validate_agent_response(text: str, tool_results: list[Any]) -> ResponseGuardResult:
    """Find rupiah values that were not present in the current tool context."""
    allowed = _allowed_amounts(tool_results)
    foreign = [
        match.group(0).strip()
        for match in _RUPIAH.finditer(str(text or ""))
        if match.group(0).replace(" ", "") not in allowed
    ]
    return ResponseGuardResult(foreign_amounts=foreign)
