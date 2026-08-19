from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "rocky-interface"
GRANITE_DIR = ROOT / "granite-llm-server"
NPM = "npm.cmd" if os.name == "nt" else "npm"
TEST_WEB_ENV = {
    "PUBLIC_APP_ENV": "testing",
    "PUBLIC_API_BASE_URL": "http://127.0.0.1:5001",
    "PUBLIC_ENABLE_DBTEST": "false",
    "PUBLIC_ENABLE_MICROSOFT_OAUTH": "false",
    "ROCKY_ENABLE_STREAMING": "false",
}


@dataclass(frozen=True)
class AcceptanceStep:
    name: str
    command: tuple[str, ...]
    cwd: Path = ROOT
    environment: dict[str, str] = field(default_factory=dict)
    pythonpath: tuple[Path, ...] = ()


def acceptance_steps(*, include_browser: bool = True) -> list[AcceptanceStep]:
    """Return the single local release-gate command matrix."""
    python = sys.executable
    steps = [
        AcceptanceStep(
            "backend tests",
            (
                python,
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
        AcceptanceStep(
            "Granite bridge tests",
            (
                python,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_*.py",
                "-v",
            ),
            cwd=GRANITE_DIR,
        ),
        AcceptanceStep(
            "frontend unit tests",
            (NPM, "run", "test:unit"),
            cwd=FRONTEND_DIR,
            environment=TEST_WEB_ENV,
        ),
        AcceptanceStep(
            "frontend type checks",
            (NPM, "run", "check"),
            cwd=FRONTEND_DIR,
            environment=TEST_WEB_ENV,
        ),
        AcceptanceStep(
            "frontend formatting",
            (NPM, "run", "lint"),
            cwd=FRONTEND_DIR,
            environment=TEST_WEB_ENV,
        ),
        AcceptanceStep(
            "frontend production build",
            (NPM, "run", "build"),
            cwd=FRONTEND_DIR,
            environment=TEST_WEB_ENV,
        ),
    ]
    if include_browser:
        steps.append(
            AcceptanceStep(
                "frontend browser tests",
                (
                    python,
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "run-test/frontend",
                    "-p",
                    "test_*.py",
                    "-v",
                ),
                environment=TEST_WEB_ENV,
                pythonpath=(ROOT / "run-test", ROOT / "rocky-backend"),
            )
        )
    return steps


def step_environment(step: AcceptanceStep) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(step.environment)
    if step.pythonpath:
        entries = [str(path) for path in step.pythonpath]
        existing = environment.get("PYTHONPATH", "").strip()
        if existing:
            entries.append(existing)
        environment["PYTHONPATH"] = os.pathsep.join(entries)
    return environment


def run_steps(
    steps: Sequence[AcceptanceStep],
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> int:
    command_runner = runner or subprocess.run
    failures: list[str] = []
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
            failures.append(step.name)
            continue
        if result.returncode == 0:
            print(f"PASS  {step.name}")
        else:
            print(f"FAIL  {step.name}: exit {result.returncode}")
            failures.append(step.name)

    if failures:
        print("\nRelease gate failed: " + ", ".join(failures) + ".")
        return 1
    print(f"\nRelease gate passed: {len(steps)} step(s).")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Rocky's local release-gate test matrix.",
    )
    parser.add_argument(
        "--skip-browser",
        action="store_true",
        help="Skip Selenium browser tests when a browser or driver is unavailable.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_steps(acceptance_steps(include_browser=not args.skip_browser))


if __name__ == "__main__":
    raise SystemExit(main())
