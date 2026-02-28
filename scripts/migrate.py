#!/usr/bin/env python3
"""
Idempotent database migration script.
Runs SQL migrations from docs/db/migrations/ in order.
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import asyncpg


def get_migrations_dir() -> str:
    """Path to migrations directory."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo_root, "docs", "db", "migrations")


def get_migration_files() -> list[str]:
    """Return sorted list of .sql migration files."""
    migrations_dir = get_migrations_dir()
    if not os.path.isdir(migrations_dir):
        return []
    files = [f for f in os.listdir(migrations_dir) if f.endswith(".sql")]
    return sorted(files)


async def migrate():
    """Run migrations from docs/db/migrations/."""
    url = os.environ.get("TRANSACTION_POOLER_URL")
    if not url:
        print("ERROR: TRANSACTION_POOLER_URL not set")
        sys.exit(1)

    migrations_dir = get_migrations_dir()
    if not os.path.isdir(migrations_dir):
        print(f"ERROR: Migrations directory not found: {migrations_dir}")
        sys.exit(1)

    files = get_migration_files()
    if not files:
        print("ERROR: No .sql migration files found")
        sys.exit(1)

    conn = await asyncpg.connect(url)

    try:
        for filename in files:
            filepath = os.path.join(migrations_dir, filename)
            with open(filepath, "r") as f:
                sql = f.read()
            name = os.path.splitext(filename)[0]
            await conn.execute(sql)
            print(f"✓ {name}")

        print("\nMigration complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    asyncio.run(migrate())
