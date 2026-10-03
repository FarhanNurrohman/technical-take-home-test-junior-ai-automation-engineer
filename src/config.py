"""Project settings and environment-backed integration configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
GOOGLE_SHEETS_CRED = os.getenv("GOOGLE_SHEETS_CRED")
SPREADSHEET_KEY = os.getenv("SPREADSHEET_KEY")

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
GL_PATH = DATA_DIR / "GL - Advances Other - April 2026.xls"
WORKING_PAPER_PATH = DATA_DIR / "Working Paper Advances and Prepayment-Soal.xlsx"

PO_PATTERNS = (r"\b[A-Z0-9]{2,}/(?:PO|WO|SPK|PGJ)/\d+\b",)
PENGAJUAN_PATTERN = (
	r"\b[A-Z][A-Z0-9-]*/(?:XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I)/\d{2,4}\b"
)
ROMAN_MONTHS = {
	"I": 1,
	"II": 2,
	"III": 3,
	"IV": 4,
	"V": 5,
	"VI": 6,
	"VII": 7,
	"VIII": 8,
	"IX": 9,
	"X": 10,
	"XI": 11,
	"XII": 12,
}
ADJUSTMENT_MODE = "net"
SIMILARITY_THRESHOLD = 0.6
AMOUNT_TOLERANCE = 0.01