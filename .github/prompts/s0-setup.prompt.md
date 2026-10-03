---
description: Tahap 0, kerangka proyek
agent: tdd-builder
---
Siapkan kerangka proyek sesuai #file:../../docs/SPEC.md dan struktur di #file:../copilot-instructions.md:
src/ (config.py, loaders.py, matcher.py, ai_summary.py, sheets_exporter.py), tests/ (conftest.py), main.py, scripts/.
Buat requirements.txt (pandas, openpyxl, xlrd, python-dotenv, gspread, google-auth, google-genai, pytest, pytest-mock, pytest-cov), .env.example (GEMINI_API_KEY, GEMINI_MODEL, GOOGLE_SHEETS_CRED, SPREADSHEET_KEY), .gitignore (.env, credentials*.json, venv/, __pycache__/, output/), dan .vscode/settings.json dengan python.testing.pytestEnabled=true dan pytestArgs=["tests"].
Buat venv, instal dependensi, jalankan `pytest -q` (0 test boleh), laporkan hasilnya.