from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Write the STS2 mod manifest JSON.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--has-pck", action="store_true")
    parser.add_argument("--has-dll", action="store_true")
    parser.add_argument("--dependency", action="append", default=[])
    parser.add_argument("--affects-gameplay", dest="affects_gameplay", action="store_true")
    parser.add_argument("--non-gameplay", dest="affects_gameplay", action="store_false")
    parser.set_defaults(affects_gameplay=True)
    args = parser.parse_args()

    payload = {
        "id": args.id,
        "name": args.name,
        "author": args.author,
        "description": args.description,
        "version": args.version,
        "has_pck": args.has_pck,
        "has_dll": args.has_dll,
        "dependencies": args.dependency,
        "affects_gameplay": args.affects_gameplay,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
