from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


LOCAL_SERVER_ENV = Path("config/server.env")


def ensure_trailing_slash(value: str) -> str:
    return value if value.endswith("/") else value + "/"


def run(command: list[str], dry_run: bool) -> int:
    print(" ".join(command))
    if dry_run:
        return 0
    return subprocess.call(command)


def rsync_base(ssh_port: str | None) -> list[str]:
    command = ["rsync", "-avz"]
    if ssh_port:
        command.extend(["-e", f"ssh -p {ssh_port}"])
    return command


def load_server_env(path: Path = LOCAL_SERVER_ENV) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    load_server_env()
    parser = argparse.ArgumentParser(
        description="Push local solution logs to the scoring server or pull scoring back."
    )
    parser.add_argument("direction", choices=["push", "pull"])
    parser.add_argument(
        "--local",
        default="logs/",
        help="Local logs directory. Defaults to logs/.",
    )
    parser.add_argument(
        "--local-results",
        default="data/results/",
        help="Local scoring results directory. Defaults to data/results/.",
    )
    parser.add_argument(
        "--remote",
        default=os.environ.get("SCORER_REMOTE_LOGS"),
        help="Remote rsync target. Defaults to SCORER_REMOTE_LOGS or config/server.env.",
    )
    parser.add_argument(
        "--ssh-port",
        default=os.environ.get("SCORER_SSH_PORT"),
        help="Optional SSH port. Defaults to SCORER_SSH_PORT or ssh default.",
    )
    parser.add_argument(
        "--remote-results",
        default=os.environ.get("SCORER_REMOTE_RESULTS"),
        help=(
            "Remote scoring-results rsync target. Defaults to SCORER_REMOTE_RESULTS. "
            "If omitted, syncs logs only."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the rsync command without running it.",
    )
    args = parser.parse_args()
    if not args.remote:
        parser.error(
            "remote is required. Set SCORER_REMOTE_LOGS, create config/server.env, "
            "or pass --remote user@host:/path/to/logs/"
        )

    local = ensure_trailing_slash(str(Path(args.local)))
    local_results = ensure_trailing_slash(str(Path(args.local_results)))
    remote = ensure_trailing_slash(args.remote)
    remote_results = ensure_trailing_slash(args.remote_results) if args.remote_results else None
    commands = []
    if args.direction == "push":
        command = rsync_base(args.ssh_port)
        command.extend(["--ignore-existing", local, remote])
        commands.append(command)
        if remote_results:
            command = rsync_base(args.ssh_port)
            command.extend(["--ignore-existing", local_results, remote_results])
            commands.append(command)
    else:
        command = rsync_base(args.ssh_port)
        command.extend([remote, local])
        commands.append(command)
        if remote_results:
            command = rsync_base(args.ssh_port)
            command.extend([remote_results, local_results])
            commands.append(command)

    exit_code = 0
    for command in commands:
        exit_code = run(command, args.dry_run) or exit_code
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
