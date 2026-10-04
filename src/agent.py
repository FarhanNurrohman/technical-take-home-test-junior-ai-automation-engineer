"""LangChain-backed conversational Finance Assistant."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src import config
from src.ai_summary import fallback_summary
from src.chat_assistant import get_summary
from src.data_source import ArtifactDataSource, DataSource, DemoDataSource
from src.guardrails import guard_question, validate_agent_response

logger = logging.getLogger(__name__)
_PROMPT_PATH = Path(__file__).parent / "prompts" / "finance_assistant.md"


def _prompt_text() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as error:
        logger.exception("Finance Assistant prompt cannot be loaded")
        raise RuntimeError("Prompt Finance Assistant tidak dapat dibaca.") from error


def _metrics(source: DataSource) -> dict[str, Any]:
    frame = source.load_flat()
    unmatched = source.load_unmatched()
    meta = source.load_meta()
    return get_summary(
        {
            "df_result": frame,
            "df_unmatched": unmatched,
            "metrics": source.artifacts.get("metrics", {}) if isinstance(source, ArtifactDataSource) else {},
            "reconcile_result": meta,
        }
    )


def _model_response(value: Any) -> str:
    content = getattr(value, "content", value)
    if isinstance(content, list):
        return "\n".join(str(part.get("text", part)) if isinstance(part, dict) else str(part) for part in content)
    return str(content or "").strip()


def _messages(system: str, payload: dict[str, Any]) -> Any:
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        return [SystemMessage(content=system), HumanMessage(content=json.dumps(payload, ensure_ascii=False))]
    except ImportError:
        return [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]


def preview_agent_payload(question: str, history: list[Any] | None, data_source: DataSource) -> dict[str, Any]:
    """Return the bounded context that will be supplied to the model."""
    summary = _metrics(data_source)
    return {
        "question": str(question or "")[:500],
        "history": list(history or [])[-10:],
        "context": summary,
        "freshness": data_source.freshness(),
    }


class FinanceAgent:
    """Small injectable LangChain model wrapper with deterministic fallback."""

    def __init__(self, llm: Any, data_source: DataSource) -> None:
        self.llm = llm
        self.data_source = data_source

    def invoke(self, question: str, history: list[Any] | None = None) -> str:
        guard = guard_question(question)
        if guard.blocked:
            return guard.message
        payload = preview_agent_payload(guard.question, history, self.data_source)
        if self.llm is None:
            return fallback_summary(self.data_source.artifacts.get("metrics", {})) if isinstance(self.data_source, ArtifactDataSource) else "Data tidak tersedia."
        model_failed = False
        try:
            response = _model_response(self.llm.invoke(_messages(_prompt_text(), payload)))
        except Exception:
            logger.exception("LangChain Finance Assistant failed")
            response = ""
            model_failed = True
        if not response:
            if isinstance(self.data_source, ArtifactDataSource):
                response = fallback_summary(self.data_source.artifacts.get("metrics", {}))
            else:
                response = "Data tidak tersedia untuk membuat jawaban.\n(dijawab tanpa AI)"
            model_failed = True
        if model_failed and "(dijawab tanpa AI)" not in response:
            response += "\n(dijawab tanpa AI)"
        checked = validate_agent_response(response, [payload["context"]])
        if checked.foreign_amounts:
            logger.warning("Model returned unverified rupiah amounts: %s", checked.foreign_amounts)
            response += "\nCatatan: angka belum terverifikasi terhadap hasil tool."
        generated_at = payload["freshness"].get("generated_at") or "waktu sumber tidak tersedia"
        return f"{response}\n\nSumber: data finance (generated_at: {generated_at})."


def build_agent(
    llm: Any = None,
    tools: list[Any] | None = None,
    checkpointer: Any = None,
    data_source: DataSource | None = None,
) -> FinanceAgent:
    """Build an injectable agent; optional tools are reserved for MCP adapters."""
    del tools, checkpointer
    source = data_source or DemoDataSource()
    if llm is None:
        if not config.GEMINI_API_KEY or not config.GEMINI_MODEL:
            return FinanceAgent(None, source)
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            llm = ChatGoogleGenerativeAI(
                model=config.GEMINI_MODEL,
                google_api_key=config.GEMINI_API_KEY,
                temperature=0.1,
                timeout=config.CHAT_TIMEOUT_SECONDS,
                max_retries=2,
            )
        except Exception as error:
            logger.exception("Unable to initialize ChatGoogleGenerativeAI")
            raise RuntimeError("Gemini LangChain tidak dapat diinisialisasi.") from error
    return FinanceAgent(llm, source)
