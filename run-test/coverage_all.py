from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "rocky-interface"
NPM = "npm.cmd" if os.name == "nt" else "npm"
FRONTEND_TEST_ENV = {
    "PUBLIC_APP_ENV": "testing",
    "PUBLIC_API_BASE_URL": "http://127.0.0.1:5001",
    "PUBLIC_ENABLE_MICROSOFT_OAUTH": "false",
    "ROCKY_ENABLE_STREAMING": "false",
}


@dataclass(frozen=True)
class CoverageStep:
    name: str
    command: tuple[str, ...]
    cwd: Path = ROOT
    environment: dict[str, str] = field(default_factory=dict)
    pythonpath: tuple[Path, ...] = ()


def coverage_steps() -> list[CoverageStep]:
    """Return the complete local code-coverage command sequence."""
    python = sys.executable
    coverage = (python, "-m", "coverage")
    return [
        CoverageStep("erase old Python coverage", (*coverage, "erase")),
        CoverageStep(
            "backend Python coverage",
            (
                *coverage,
                "run",
                "-m",
                "unittest",
                "discover",
                "-s",
                "run-test/backend",
                "-p",
                "test_*.py",
                "-v",
            ),
            pythonpath=(ROOT / "rocky-backend",),
        ),
        CoverageStep(
            "Granite Python coverage",
            (
                *coverage,
                "run",
                "-m",
                "unittest",
                "discover",
                "-s",
                "granite-llm-server/tests",
                "-p",
                "test_*.py",
                "-v",
            ),
            pythonpath=(ROOT / "granite-llm-server",),
        ),
        CoverageStep("combine Python coverage", (*coverage, "combine")),
        CoverageStep("report Python coverage", (*coverage, "report")),
        CoverageStep(
            "frontend coverage",
            (NPM, "run", "test:coverage"),
            cwd=FRONTEND_DIR,
            environment=FRONTEND_TEST_ENV,
        ),
    ]


def step_environment(step: CoverageStep) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(step.environment)
    environment["COVERAGE_RCFILE"] = str(ROOT / ".coveragerc")
    environment["COVERAGE_FILE"] = str(ROOT / ".coverage")
    if step.pythonpath:
        entries = [str(path) for path in step.pythonpath]
        existing = environment.get("PYTHONPATH", "").strip()
        if existing:
            entries.append(existing)
        environment["PYTHONPATH"] = os.pathsep.join(entries)
    return environment


def run_steps(
    steps: Sequence[CoverageStep],
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> int:
    command_runner = runner or subprocess.run
    for index, step in enumerate(steps, start=1):
        print(f"\n[{index}/{len(steps)}] {step.name}", flush=True)
        try:
            result = command_runner(
                list(step.command),
                cwd=step.cwd,
                env=step_environment(step),
                check=False,
            )
        except OSError as error:
            print(f"FAIL  {step.name}: {type(error).__name__}: {error}")
            return 1
        if result.returncode != 0:
            print(f"FAIL  {step.name}: exit {result.returncode}")
            return 1
        print(f"PASS  {step.name}")

    print(f"\nCoverage checks passed: {len(steps)} step(s).")
    return 0


def main() -> int:
    return run_steps(coverage_steps())


if __name__ == "__main__":
    raise SystemExit(main())
