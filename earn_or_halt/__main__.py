from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import Config
from .orchestrator import run
from .storage import Storage
from .util import read_json


def main() -> int:
    parser = argparse.ArgumentParser(prog="earn-or-halt")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("run", help="run the API and economic worker")
    subparsers.add_parser("status", help="print the persisted runtime state")
    subparsers.add_parser("clear-halt", help="clear the persistent halt flag")
    args = parser.parse_args()
    command = args.command or "run"
    config = Config.from_env()

    if command == "run":
        return run(config)
    storage = Storage(config.data_dir / "earn-or-halt.sqlite3")
    if command == "clear-halt":
        storage.clear_halt()
        print("halt flag cleared")
        return 0
    if command == "status":
        state = read_json(config.data_dir / "runtime-state.json", {}) or {}
        state["stats"] = storage.stats()
        state["halt_reason"] = storage.halt_reason()
        print(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    parser.error(f"unknown command: {command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
