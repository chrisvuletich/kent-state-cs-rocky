from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from rocky_tools.doctor import RockyDoctor
from rocky_tools.database_counts import collect_database_counts, render_database_counts
from rocky_tools.retention import RequestRetention, parse_before_date
from run_env import load_env_file, load_project_env


ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "rocky-backend"
FRONTEND_DIR = ROOT / "rocky-interface"
GRANITE_DIR = ROOT / "granite-llm-server"
CHAT_API_DIR = ROOT / "api-rocky"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rocky maintenance commands.")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser(
        "doctor",
        help="Validate configuration and service connectivity without changing data.",
    )
    doctor.add_argument(
        "--env-file",
        action="append",
        default=[],
        type=Path,
        help="Additional environment file to load. May be supplied more than once.",
    )
    doctor.add_argument(
        "--timeout",
        type=float,
        default=3,
        help="Per-service timeout in seconds (default: 3).",
    )
    doctor.add_argument(
        "--skip-network",
        action="store_true",
        help="Run configuration checks without connecting to services.",
    )
    doctor.add_argument(
        "--deployment-files",
        action="store_true",
        help="Also validate installed deployment files for --deployment-host.",
    )
    doctor.add_argument(
        "--deployment-files-only",
        action="store_true",
        help="Validate only installed deployment files (useful on the Granite host).",
    )
    doctor.add_argument(
        "--deployment-host",
        choices=("rocky", "granite", "all"),
        default="rocky",
        help="Installed files to validate (default: rocky).",
    )
    doctor.add_argument(
        "--granite-unit",
        type=Path,
        default=Path("/etc/systemd/system/rocky-granite.service"),
        help="Installed Granite systemd unit path.",
    )
    doctor.add_argument(
        "--chat-unit",
        type=Path,
        default=Path("/etc/systemd/system/rocky-chat-api.service"),
        help="Installed chat API systemd unit path.",
    )
    doctor.add_argument(
        "--nginx-config",
        type=Path,
        default=Path("/etc/nginx/sites-enabled/rocky.cs.kent.edu.conf"),
        help="Installed Rocky Nginx config path.",
    )
    purge = commands.add_parser(
        "purge-requests",
        help="Find or delete telemetry requests older than an explicit date.",
    )
    purge.add_argument(
        "--before",
        required=True,
        help="UTC cutoff date in YYYY-MM-DD format. The cutoff itself is retained.",
    )
    purge.add_argument(
        "--apply",
        action="store_true",
        help="Delete the matched records. Without this flag the command is read-only.",
    )
    purge.add_argument(
        "--env-file",
        action="append",
        default=[],
        type=Path,
        help="Additional environment file to load. May be supplied more than once.",
    )
    counts = commands.add_parser(
        "database-counts",
        help="Print read-only document counts for backup and restore verification.",
    )
    counts.add_argument(
        "--env-file",
        action="append",
        default=[],
        type=Path,
        help="Additional environment file to load. May be supplied more than once.",
    )
    counts.add_argument(
        "--database",
        help="Override ROCKY_DB_NAME, for example when checking a temporary restore.",
    )
    return parser


def load_command_environment(paths: list[Path]) -> bool:
    load_project_env(ROOT, BACKEND_DIR, FRONTEND_DIR, GRANITE_DIR, CHAT_API_DIR)
    for path in paths:
        if not path.is_file():
            print(f"FAIL  environment file: {path} does not exist.", file=sys.stderr)
            return False
        load_env_file(path, override=True)
    return True


def run_doctor(args: argparse.Namespace) -> int:
    if not load_command_environment(args.env_file):
        return 2

    if args.timeout <= 0:
        print("FAIL  configuration: --timeout must be greater than zero.", file=sys.stderr)
        return 2

    deployment_files = None
    if args.deployment_files or args.deployment_files_only:
        deployment_files = {}
        if args.deployment_host in {"granite", "all"}:
            deployment_files["granite"] = args.granite_unit
        if args.deployment_host in {"rocky", "all"}:
            deployment_files.update({
                "chat": args.chat_unit,
                "nginx": args.nginx_config,
            })

    doctor = RockyDoctor(
        timeout_seconds=args.timeout,
        include_network=not args.skip_network,
        deployment_files=deployment_files,
    )
    checks = (
        doctor.deployment_file_checks()
        if args.deployment_files_only
        else doctor.run()
    )
    for check in checks:
        print(f"{check.status:<4}  {check.name}: {check.detail}")
    return 1 if any(check.failed for check in checks) else 0


def _display_timestamp(value) -> str:
    return value.isoformat().replace("+00:00", "Z") if value else "N/A"


def run_purge_requests(args: argparse.Namespace) -> int:
    if not load_command_environment(args.env_file):
        return 2
    try:
        cutoff = parse_before_date(args.before)
    except ValueError as error:
        print(f"FAIL  retention cutoff: {error}", file=sys.stderr)
        return 2

    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    try:
        from backend.config import get_settings
        from backend.storage import build_collections

        collections = build_collections(get_settings())
        result = RequestRetention(
            collections.telemetry_interactions,
            collections.api_history,
        ).run(cutoff, apply=args.apply)
    except Exception as error:
        print(
            f"FAIL  telemetry retention: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1

    print(f"Cutoff (UTC): {result.cutoff.date().isoformat()}")
    print(f"Requests matched: {result.matched:,}")
    print(f"Oldest: {_display_timestamp(result.oldest)}")
    print(f"Newest: {_display_timestamp(result.newest)}")
    if result.applied:
        print(f"Requests deleted: {result.deleted:,}")
        print("An audit event was recorded in api_history.")
        return 0 if result.deleted == result.matched else 1
    print("No data was deleted. Take a backup, then re-run with --apply to proceed.")
    return 0


def run_database_counts(args: argparse.Namespace) -> int:
    if not load_command_environment(args.env_file):
        return 2

    database_override = (args.database or "").strip()
    if database_override:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", database_override):
            print(
                "FAIL  database name: use only letters, numbers, underscores, and hyphens.",
                file=sys.stderr,
            )
            return 2
        os.environ["ROCKY_DB_NAME"] = database_override

    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    try:
        from backend.config import get_settings
        from backend.storage import build_collections

        settings = get_settings()
        collections = build_collections(settings)
        counts = collect_database_counts(collections)
    except Exception as error:
        print(
            f"FAIL  database counts: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1

    print(f"Database: {settings.db_name}")
    print(f"Backend: {settings.db_backend}")
    for line in render_database_counts(counts):
        print(line)
    print(f"{'TOTAL':<24} {sum(count.documents for count in counts):>12,}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return run_doctor(args)
    if args.command == "purge-requests":
        return run_purge_requests(args)
    if args.command == "database-counts":
        return run_database_counts(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
