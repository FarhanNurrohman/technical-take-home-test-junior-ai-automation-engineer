---
description: Tahap 5, orkestrasi, e2e, README
agent: tdd-builder
---
Rapikan main.py jadi orkestrator tipis: load -> match -> aggregate -> reconcile -> summary -> export, dengan CLI --dry-run (tulis output/result.xlsx dan cetak ringkasan, tanpa Gemini dan Sheets) dan --no-ai. Log tiap tahap (jumlah baris, durasi); exit code non-zero bila reconcile gagal.
Tambahkan tests/test_e2e.py (data sintetis, Gemini dan gspread di-mock). Jalankan `pytest -q --cov=src` sampai hijau, target cakupan matcher.py >= 90%. Jalankan `python main.py --dry-run` pada file asli dan tunjukkan hasilnya.
Terakhir perbarui README.md (setup, logika matching, pengujian, penggunaan Copilot, asumsi) dan daftar asumsi yang perlu saya verifikasi.