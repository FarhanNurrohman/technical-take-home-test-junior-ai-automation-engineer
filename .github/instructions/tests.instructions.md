---
applyTo: "tests/**/*.py"
---
- Gunakan pytest dan fixture di conftest.py dengan data sintetis kecil di tmp_path.
- Mock Gemini dan gspread dengan pytest-mock; test dilarang memakai jaringan.
- Satu perilaku per test, nama deskriptif (test_multi_voucher_merges_and_sums).
- Test dengan file asli ditandai skipif jika file tidak ada.