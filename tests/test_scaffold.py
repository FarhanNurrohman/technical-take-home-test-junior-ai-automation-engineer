import importlib


def test_application_modules_are_importable():
    modules = (
        "src.config",
        "src.loaders",
        "src.matcher",
        "src.ai_summary",
        "src.sheets_exporter",
        "main",
    )

    for module in modules:
        importlib.import_module(module)