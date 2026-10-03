---
description: Tahap 3, Executive Summary Gemini
agent: tdd-builder
---
Kerjakan src/ai_summary.py + tests/test_ai_summary.py dengan SDK google-genai; model dan key dari .env (GEMINI_MODEL, GEMINI_API_KEY).
1. compute_metrics(df_result, period="April 2026"): total_advance, total_realization, total_balance, unsettled_count, unsettled_items (description, amount, realized, balance, status), over_settled_items, unmatched_gl_total, semua dihitung di Python.
2. build_prompt(metrics): Executive Summary Indonesia, Markdown, 3 bagian (Executive Overview, Detail Item Unsettled dengan nominal, Rekomendasi Tindak Lanjut). Tegaskan: gunakan HANYA angka pada data.
3. generate_executive_summary(df_result, client=None): timeout, retry maks 2x; bila gagal/kosong -> fallback template Python bertanda "(dibuat otomatis tanpa AI)". Bila total tidak muncul di teks, tambahkan tabel KPI deterministik.
Test dengan Gemini di-mock: metrics benar (termasuk semua SETTLED), prompt memuat item unsettled, sukses, dan fallback saat error/timeout/kosong. Jalankan sampai hijau, lalu satu kali dengan API asli dan tampilkan hasilnya.