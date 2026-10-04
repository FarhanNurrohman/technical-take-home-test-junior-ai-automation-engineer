"""Optional local Gradio interface for Google Sheets settlement reports."""

from __future__ import annotations

import argparse
import logging
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from src.artifacts import load_artifacts
from src.ai_summary import compute_metrics
from src.chat_assistant import answer, fallback_answer
from src.config import CHAT_AUTH_PASS, CHAT_AUTH_USER, CHAT_RATE_LIMIT_PER_MIN, ROOT_DIR
from src.sheets_chat_loader import load_chat_artifacts_from_sheets

logger = logging.getLogger(__name__)


def demo_artifacts() -> dict[str, Any]:
    """Return a small synthetic data set for UI/demo validation only."""
    import pandas as pd

    result = pd.DataFrame(
        [
            {"target_id": "WP-DEMO-1", "section": "WP", "description": "STYLING SM 1132 (2 BEDROOM)", "amount": 25_695_900, "realization_amount": 2_028_300, "balance": 23_667_600, "status": "PARTIAL", "need_settlement_evidence": True, "settlement_total": 0, "refund_total": 2_028_300},
            {"target_id": "WP-DEMO-2", "section": "WP", "description": "STYLING SM 1127 (STUDIO)", "amount": 1_583_700, "realization_amount": 268_000, "balance": 1_315_700, "status": "PARTIAL", "need_settlement_evidence": True, "settlement_total": 0, "refund_total": 308_000},
            {"target_id": "WP-DEMO-3", "section": "WP", "description": "PBB JV 2 SUMMARECON", "amount": 500_000, "realization_amount": 0, "balance": 500_000, "status": "UNSETTLED"},
        ]
    )
    unmatched = pd.DataFrame()
    reconcile_result = {"diff_total": 0, "reconcile_diff": 0, "reconcile_ok": True}
    return {
        "df_result": result,
        "df_unmatched": unmatched,
        "metrics": compute_metrics(result, reconcile_result, unmatched),
        "reconcile_result": reconcile_result,
    }


def load_chat_data(*, source: str = "sheets", demo: bool = False) -> tuple[dict[str, Any], str]:
    """Load one startup snapshot from demo, Google Sheets, or local artifacts."""
    if demo:
        return demo_artifacts(), "MODE DEMO: data sintetis"
    if source == "sheets":
        return load_chat_artifacts_from_sheets(), "Data Google Sheets (snapshot saat app dijalankan)"
    if source == "artifacts":
        return load_artifacts(ROOT_DIR / "output"), "Data nyata dari output/"
    raise ValueError("source harus 'sheets' atau 'artifacts'.")


def create_chat_handler(artifacts: dict[str, Any], *, use_ai: bool = True):
    """Create a testable response callable with per-session rate limiting."""
    requests: dict[str, deque[float]] = defaultdict(deque)

    def respond(message: str, history: list[Any] | None = None, session_id: str | None = None) -> str:
        now = time.monotonic()
        key = str(session_id or "local-session")
        recent = requests[key]
        while recent and now - recent[0] >= 60:
            recent.popleft()
        if len(recent) >= CHAT_RATE_LIMIT_PER_MIN:
            return f"Batas {CHAT_RATE_LIMIT_PER_MIN} pertanyaan per menit tercapai untuk sesi ini."
        recent.append(now)
        question = str(message or "")[:500]
        if not question.strip():
            return "Masukkan pertanyaan tentang hasil settlement."
        return answer(question, history or [], artifacts) if use_ai else fallback_answer(question, artifacts)

    return respond


def create_interface(artifacts: dict[str, Any], *, use_ai: bool, data_status: str):
    """Create, but do not launch, the Gradio ChatInterface."""
    import gradio as gr
    from gradio.context import LocalContext

    handler = create_chat_handler(artifacts, use_ai=use_ai)

    def respond(message: str, history: list[Any]) -> str:
        request = LocalContext.request.get(None)
        session_id = getattr(request, "session_hash", None)
        return handler(message, history, session_id)

    return gr.ChatInterface(
        fn=respond,
        title="Finance Assistant: Advance & Prepayment",
        examples=[
            "Buat ringkasan posisi settlement.",
            "Item apa yang masih punya saldo?",
            "Berapa total advance awal?",
            "Kenapa Styling 2 Bedroom belum selesai?",
        ],
        chatbot=gr.Chatbot(),
        analytics_enabled=False,
        description=(
            f"Status: {data_status}\n\n"
            "Jawaban AI mengirim pertanyaan, ringkasan angka, dan hasil tool terkait ke Gemini. "
            "Jangan masukkan kredensial atau data sensitif."
        ),
    )


def launch_chat(artifacts: dict[str, Any], *, use_ai: bool, data_status: str) -> None:
    """Launch the Gradio chat using an already loaded artifact snapshot."""
    interface = create_interface(artifacts, use_ai=use_ai, data_status=data_status)
    auth = (CHAT_AUTH_USER, CHAT_AUTH_PASS) if CHAT_AUTH_USER and CHAT_AUTH_PASS else None
    interface.launch(server_name="127.0.0.1", share=False, auth=auth)


def main() -> int:
    parser = argparse.ArgumentParser(description="Chat lokal untuk hasil settlement")
    parser.add_argument("--demo", action="store_true", help="Gunakan data sintetis, bukan artifacts nyata")
    parser.add_argument("--no-ai", action="store_true", help="Jawab dari tool deterministik tanpa Gemini")
    parser.add_argument("--check", action="store_true", help="Validasi payload tanpa menjalankan server")
    parser.add_argument("--source", choices=("sheets", "artifacts"), default="sheets", help="Sumber data nyata; default Google Sheets")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    try:
        artifacts, status = load_chat_data(source=arguments.source, demo=arguments.demo)
    except (FileNotFoundError, PermissionError, RuntimeError, ValueError) as error:
        print(f"Sumber data chatbot belum dapat dibaca: {error}")
        if arguments.source == "artifacts" and not arguments.demo:
            print("Jalankan python main.py --dry-run untuk membuat output/result.json terlebih dahulu.")
        else:
            print("Periksa SPREADSHEET_KEY, GOOGLE_SHEETS_CRED, tab report, dan izin baca Google Sheets di .env.")
        return 1

    if arguments.check:
        print(f"Payload valid: {status}; {len(artifacts['df_result'])} baris hasil.")
        return 0

    try:
        import gradio as gr
    except ImportError:
        logger.error("Gradio tidak terpasang. Install dependensi dari requirements.txt.")
        return 1
    launch_chat(artifacts, use_ai=not arguments.no_ai, data_status=status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())