"""List Gemini models that support generateContent."""

from __future__ import annotations

import os


def main() -> None:
	"""Print supported model names without exposing credentials."""
	from google import genai

	api_key = os.getenv("GEMINI_API_KEY")
	if not api_key:
		raise SystemExit("GEMINI_API_KEY belum dikonfigurasi.")
	client = genai.Client(api_key=api_key)
	for model in client.models.list():
		supported = getattr(model, "supported_actions", None) or getattr(model, "supported_generation_methods", None) or []
		if "generateContent" in supported or "generate_content" in supported:
			print(getattr(model, "name", ""))


if __name__ == "__main__":
	main()
