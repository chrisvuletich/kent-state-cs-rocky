from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "run-test" / "test_all.py"


def load_module():
    spec = importlib.util.spec_from_file_location("rocky_acceptance_runner", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the Rocky acceptance runner.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


acceptance = load_module()


class AcceptanceRunnerTests(unittest.TestCase):
    def test_full_matrix_covers_every_repository_test_surface(self):
        steps = acceptance.acceptance_steps()

        self.assertEqual(
            [step.name for step in steps],
            [
                "backend tests",
                "Granite bridge tests",
                "frontend unit tests",
                "frontend type checks",
                "frontend formatting",
                "frontend production build",
                "frontend browser tests",
            ],
        )
        self.assertEqual(steps[0].cwd, ROOT)
        self.assertEqual(steps[1].cwd, ROOT / "granite-llm-server")
        self.assertEqual(steps[-1].cwd, ROOT)

    def test_skip_browser_retains_all_non_browser_release_checks(self):
        steps = acceptance.acceptance_steps(include_browser=False)

        self.assertEqual(len(steps), 6)
        self.assertNotIn("frontend browser tests", [step.name for step in steps])

    def test_frontend_steps_pin_streaming_to_the_buffered_test_baseline(self):
        frontend_steps = [
            step
            for step in acceptance.acceptance_steps()
            if step.cwd == ROOT / "rocky-interface" or step.name == "frontend browser tests"
        ]

        self.assertTrue(frontend_steps)
        for step in frontend_steps:
            with self.subTest(step=step.name):
                self.assertEqual(step.environment["ROCKY_ENABLE_STREAMING"], "false")

        with patch.dict(os.environ, {"ROCKY_ENABLE_STREAMING": "true"}):
            environment = acceptance.step_environment(frontend_steps[0])
        self.assertEqual(environment["ROCKY_ENABLE_STREAMING"], "false")

    def test_runner_continues_after_failure_and_returns_nonzero(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(
                command,
                2 if len(calls) == 1 else 0,
            )

        steps = acceptance.acceptance_steps(include_browser=False)[:2]
        with redirect_stdout(io.StringIO()):
            result = acceptance.run_steps(steps, runner=runner)

        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 2)
        backend_environment = calls[0][1]["env"]
        self.assertEqual(
            backend_environment["PYTHONPATH"].split(os.pathsep)[0],
            str(ROOT / "rocky-backend"),
        )

    def test_runner_reports_missing_executable_without_a_traceback(self):
        def runner(_command, **_kwargs):
            raise FileNotFoundError("missing test executable")

        step = acceptance.acceptance_steps(include_browser=False)[0]

        with redirect_stdout(io.StringIO()):
            result = acceptance.run_steps([step], runner=runner)

        self.assertEqual(result, 1)

    def test_main_flag_excludes_browser(self):
        with patch.object(acceptance, "run_steps", return_value=0) as run_steps:
            result = acceptance.main(["--skip-browser"])

        self.assertEqual(result, 0)
        submitted = run_steps.call_args.args[0]
        self.assertNotIn("frontend browser tests", [step.name for step in submitted])

    def test_ci_log_pipelines_propagate_python_test_failures(self):
        workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
            encoding="utf-8"
        )

        self.assertEqual(workflow.count("set -o pipefail"), 2)
        self.assertEqual(workflow.count('2>&1 | tee run-test/logs/'), 2)


if __name__ == "__main__":
    unittest.main()
