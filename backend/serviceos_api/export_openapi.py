"""Generate or check the contract directly from the actual FastAPI application."""

import argparse
import json
from pathlib import Path

from serviceos_api.main import create_app


def render_contract() -> str:
    return json.dumps(create_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare without changing the contract")
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parents[2] / "contracts" / "openapi.json",
    )
    args = parser.parse_args()
    expected = render_contract()
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != expected:
            print("OpenAPI differs from the application. Run the export command.")
            return 1
        print("OpenAPI matches the actual application.")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(expected, encoding="utf-8", newline="\n")
    print(f"Exported {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
