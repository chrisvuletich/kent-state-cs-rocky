from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "run-test" / "coverage_all.py"


def load_module():
    spec = importlib.util.spec_from_file_location("rocky_coverage_runner", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the Rocky coverage runner.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


coverage_runner = load_module()


class CoverageRunnerTests(unittest.TestCase):
    def test_matrix_covers_python_and_frontend_sources(self):
        steps = coverage_runner.coverage_steps()

        self.assertEqual(
            [step.name for step in steps],
            [
                "erase old Python coverage",
                "backend Python coverage",
                "Granite Python coverage",
                "combine Python coverage",
                "report Python coverage",
                "frontend coverage",
            ],
        )
        self.assertEqual(steps[-1].cwd, ROOT / "rocky-interface")
        self.assertEqual(
            steps[-1].command,
            (coverage_runner.NPM, "run", "test:coverage"),
        )

    def test_python_steps_use_repository_coverage_files_and_import_paths(self):
        backend_step, granite_step = coverage_runner.coverage_steps()[1:3]

        backend_environment = coverage_runner.step_environment(backend_step)
        granite_environment = coverage_runner.step_environment(granite_step)

        self.assertEqual(
            backend_environment["COVERAGE_RCFILE"],
            str(ROOT / ".coveragerc"),
        )
        self.assertEqual(backend_environment["COVERAGE_FILE"], str(ROOT / ".coverage"))
        self.assertEqual(
            backend_environment["PYTHONPATH"].split(os.pathsep)[0],
            str(ROOT / "rocky-backend"),
        )
        self.assertEqual(
            granite_environment["PYTHONPATH"].split(os.pathsep)[0],
            str(ROOT / "granite-llm-server"),
        )

    def test_runner_stops_after_a_failed_step(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 2)

        with redirect_stdout(io.StringIO()):
            result = coverage_runner.run_steps(
                coverage_runner.coverage_steps(),
                runner=runner,
            )

        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 1)

    def test_runner_reports_missing_executable_without_a_traceback(self):
        def runner(_command, **_kwargs):
            raise FileNotFoundError("missing coverage executable")

        with redirect_stdout(io.StringIO()):
            result = coverage_runner.run_steps(
                coverage_runner.coverage_steps()[:1],
                runner=runner,
            )

        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
