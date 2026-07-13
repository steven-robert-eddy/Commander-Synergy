"""Command-line interface for the synergy finder."""

from __future__ import annotations

import argparse
import sys

import requests

from . import bulk_data, db


def _cmd_update_data(args: argparse.Namespace) -> int:
    print("Checking Scryfall bulk data...")
    try:
        json_path = bulk_data.download_oracle_cards(force=args.force)
    except requests.exceptions.RequestException as exc:
        print(f"Failed to reach Scryfall: {exc}", file=sys.stderr)
        return 1
    print(f"Oracle cards JSON ready at {json_path}")

    print("Building local SQLite database...")
    cards = bulk_data.load_cards(json_path)
    db_path = db.build_database(cards=cards)
    print(f"Loaded {len(cards)} cards into {db_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synergy-finder",
        description="Find mechanically synergistic MTG cards using rule-based oracle text analysis.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    update_parser = subparsers.add_parser(
        "update-data", help="Download the latest Scryfall oracle_cards bulk data and rebuild the local DB."
    )
    update_parser.add_argument(
        "--force", action="store_true", help="Re-download even if the local cache looks fresh."
    )
    update_parser.set_defaults(func=_cmd_update_data)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
