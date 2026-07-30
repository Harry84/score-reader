"""CLI entry point for Phase 0: apply the Postgres schema and, optionally,
import the existing SQLite databases into it.

Usage:
    python -m db.run_migration
    python -m db.run_migration --ref squadrons_reference.db --stats squadrons_stats.db
"""

import argparse
import os

import psycopg2
from dotenv import load_dotenv

from db.migrate_runner import apply_schema
from db.sqlite_migration import migrate


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", help="Path to squadrons_reference.db to import")
    parser.add_argument("--stats", help="Path to squadrons_stats.db to import")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="Postgres connection string (defaults to DATABASE_URL env var)",
    )
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("No database URL: set DATABASE_URL or pass --database-url")

    conn = psycopg2.connect(args.database_url)
    try:
        print("Applying schema...")
        apply_schema(conn)
        print("Schema up to date.")

        if args.ref and args.stats:
            print(f"Importing {args.ref} and {args.stats}...")
            counts = migrate(args.ref, args.stats, conn)
            for table, count in counts.items():
                print(f"  {table}: {count} rows")
        elif args.ref or args.stats:
            raise SystemExit("--ref and --stats must be given together")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
