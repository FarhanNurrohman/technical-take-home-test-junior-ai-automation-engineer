"""Environment-backed configuration for external integrations."""

import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
GOOGLE_SHEETS_CRED = os.getenv("GOOGLE_SHEETS_CRED")
SPREADSHEET_KEY = os.getenv("SPREADSHEET_KEY")