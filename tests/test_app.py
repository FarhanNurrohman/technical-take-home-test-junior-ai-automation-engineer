from __future__ import annotations

from src.chat_assistant import fallback_answer
from app import create_chat_handler, create_interface, demo_artifacts


def test_chat_handler_truncates_long_question_and_uses_answer(chat_artifacts, mocker):
    answer_mock = mocker.patch("app.answer", return_value="jawaban")
    handler = create_chat_handler(chat_artifacts, use_ai=True)

    result = handler("x" * 520, [], "session-a")

    assert result == "jawaban"
    assert len(answer_mock.call_args.args[0]) == 500


def test_chat_handler_rate_limits_per_session(chat_artifacts, mocker):
    mocker.patch("app.answer", return_value="jawaban")
    handler = create_chat_handler(chat_artifacts, use_ai=True)
    outputs = [handler("saldo", [], "session-a") for _ in range(11)]

    assert "Batas" in outputs[-1]
    assert outputs[-2] == "jawaban"


def test_chat_handler_supports_no_ai(chat_artifacts, mocker):
    fallback = mocker.patch("app.fallback_answer", wraps=fallback_answer)
    handler = create_chat_handler(chat_artifacts, use_ai=False)

    response = handler("Berapa total advance awal?", [], "session-b")

    fallback.assert_called_once()
    assert "dijawab tanpa AI" in response


def test_interface_builds_chatinterface_without_launching_server(chat_artifacts):
    import gradio as gr

    interface = create_interface(chat_artifacts, use_ai=False, data_status="MODE DEMO: data sintetis")

    assert isinstance(interface, gr.ChatInterface)
    assert interface.share is False
    assert interface.additional_inputs == []
    assert interface.analytics_enabled is False


def test_demo_answers_documented_styling_question_with_synthetic_case():
    response = create_chat_handler(demo_artifacts(), use_ai=False)(
        "Kenapa Styling 2 Bedroom belum selesai?", [], "demo-session"
    )

    assert "STYLING SM 1132 (2 BEDROOM)" in response
    assert "Rp 23.667.600" in response


def test_app_source_loader_uses_google_sheets_by_default(mocker, chat_artifacts):
    import app

    sheet_loader = mocker.patch("app.load_chat_artifacts_from_sheets", return_value=chat_artifacts)

    artifacts, status = app.load_chat_data()

    assert artifacts is chat_artifacts
    assert status.startswith("Data Google Sheets")
    sheet_loader.assert_called_once_with()


def test_demo_source_bypasses_google_sheets(mocker):
    import app

    sheet_loader = mocker.patch("app.load_chat_artifacts_from_sheets")

    artifacts, status = app.load_chat_data(demo=True)

    assert status == "MODE DEMO: data sintetis"
    assert len(artifacts["df_result"]) == 3
    sheet_loader.assert_not_called()


def test_demo_summary_includes_open_items_and_actions():
    response = create_chat_handler(demo_artifacts(), use_ai=False)(
        "Buat ringkasan posisi settlement", [], "demo-summary"
    )

    assert "STYLING SM 1132 (2 BEDROOM)" in response
    assert "PBB JV 2 SUMMARECON" in response
    assert "get_summary" in response
    assert "konfirmasi jadwal penagihan atau pembayaran" in response