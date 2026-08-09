from __future__ import annotations

import importlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_modules(package: str) -> list[str]:
    return [
        f"{package}.{path.stem}"
        for path in sorted((ROOT / package).glob("test_*.py"))
        if path.stem != "test_support"
    ]


def load_suite() -> unittest.TestSuite:
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite()
    for module_name in test_modules("backend") + test_modules("frontend"):
        module = importlib.import_module(module_name)
        suite.addTests(loader.loadTestsFromModule(module))
    return suite


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(load_suite())
    raise SystemExit(0 if result.wasSuccessful() else 1)
