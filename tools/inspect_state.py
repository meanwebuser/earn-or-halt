#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", type=Path, nargs="?", default=Path("./data"))
    args = parser.parse_args()
    state_path = args.data_dir / "runtime-state.json"
    if state_path.exists():
        print(state_path.read_text(encoding="utf-8"))
    database = args.data_dir / "earn-or-halt.sqlite3"
    if database.exists():
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT id, created_at, status, price_cents, actual_cost_cents, error FROM jobs ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
        print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
