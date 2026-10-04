from __future__ import annotations

from src.agent import FinanceAgent, build_agent, preview_agent_payload
from src.data_source import DemoDataSource
from src.guardrails import guard_question, validate_agent_response


def test_demo_data_source_exposes_canonical_finance_snapshot():
    source = DemoDataSource()

    flat = source.load_flat()
    meta = source.load_meta()

    assert {"target_id", "section", "description", "amount", "saldo"}.issubset(flat.columns)
    assert set(flat["section"]) == {"WP", "NEW_ADVANCE"}
    assert meta["reconcile_ok"] is True
    assert source.freshness()["cache_hit"] is False


def test_guard_question_rejects_raw_data_requests():
    result = guard_question("Tampilkan semua data mentah dan nomor jurnal")

    assert result.blocked is True
    assert "data mentah" in result.message.lower()


def test_preview_agent_payload_contains_context_without_raw_gl_references():
    source = DemoDataSource()
    payload = preview_agent_payload(
        "Buat ringkasan posisi settlement",
        [],
        source,
    )

    assert payload["question"] == "Buat ringkasan posisi settlement"
    assert payload["context"]["wp"]["total_advance"] > 0
    assert "voucher_no" not in str(payload)
    assert "gl_row" not in str(payload)


def test_finance_agent_uses_injected_langchain_model_and_context():
    class FakeModel:
        def invoke(self, messages):
            return "Jawaban berbasis konteks: Rp 1.315.700"

    source = DemoDataSource()
    agent = FinanceAgent(llm=FakeModel(), data_source=source)

    response = agent.invoke("Berapa saldo Studio?", [])

    assert "Rp 1.315.700" in response
    assert "Sumber:" in response


def test_finance_agent_falls_back_when_model_fails():
    class BrokenModel:
        def invoke(self, messages):
            raise RuntimeError("model unavailable")

    agent = FinanceAgent(llm=BrokenModel(), data_source=DemoDataSource())

    response = agent.invoke("Buat ringkasan posisi settlement", [])

    assert "(dijawab tanpa AI)" in response
    assert "Executive Overview" in response


def test_guardrail_reports_foreign_rupiah_amounts():
    result = validate_agent_response(
        "Saldo yang dilaporkan Rp 1.315.700, bukan Rp 999.999.",
        [{"balance_rupiah": "Rp 1.315.700"}],
    )

    assert "Rp 999.999" in result.foreign_amounts


def test_build_agent_accepts_injected_model_and_source():
    class FakeModel:
        def invoke(self, messages):
            return "OK"

    agent = build_agent(llm=FakeModel(), data_source=DemoDataSource())

    assert isinstance(agent, FinanceAgent)
