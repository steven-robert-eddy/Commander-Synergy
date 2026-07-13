"""Command-line interface for the synergy finder."""

from __future__ import annotations

import argparse
import sys

import requests

from . import bulk_data, db, tags


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


def _cmd_retag(args: argparse.Namespace) -> int:
    conn = db.connect()
    try:
        db.populate_tags(conn)
    finally:
        conn.close()
    print(f"Retagged all cards in {db.DB_PATH}")
    return 0


def _cmd_tag(args: argparse.Namespace) -> int:
    conn = db.connect()
    try:
        row = db.get_card_by_name(conn, args.name)
        if row is None:
            print(f"No card found matching {args.name!r}", file=sys.stderr)
            return 1
        matched = tags.tag_card(row)
        creature_types = tags.extract_creature_types(row["type_line"])
    finally:
        conn.close()

    print(f"{row['name']} ({row['type_line']})")
    if creature_types:
        print(f"  Creature types: {', '.join(sorted(creature_types))}")
    if matched:
        print("  Tags:")
        for tag_id in sorted(matched, key=tags.tag_weight, reverse=True):
            print(f"    - {tags.tag_label(tag_id)} [{tag_id}] (weight {tags.tag_weight(tag_id)})")
    else:
        print("  Tags: (none matched)")
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

    retag_parser = subparsers.add_parser(
        "retag", help="Recompute mechanical theme tags for every card already in the local DB."
    )
    retag_parser.set_defaults(func=_cmd_retag)

    tag_parser = subparsers.add_parser(
        "tag", help="Show the mechanical theme tags matched for a single card, by name."
    )
    tag_parser.add_argument("name", help="Card name (exact or prefix match, case-insensitive).")
    tag_parser.set_defaults(func=_cmd_tag)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
