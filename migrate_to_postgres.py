#!/usr/bin/env python3
"""
Migration script to transfer data from SQLite to PostgreSQL.

Usage:
    python migrate_to_postgres.py --sqlite ./data/shrimpicus.db --postgres postgresql://user:pass@host/db

This script:
1. Reads all data from the SQLite database
2. Creates tables in PostgreSQL (if not exists)
3. Copies all data to PostgreSQL
4. Verifies row counts match
"""

import argparse
import sqlite3
import sys
from pathlib import Path

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("Error: psycopg2-binary is required for PostgreSQL migration.")
    print("Install with: pip install psycopg2-binary")
    sys.exit(1)


def connect_sqlite(db_path: Path) -> sqlite3.Connection:
    """Connect to SQLite database."""
    if not db_path.exists():
        print(f"Error: SQLite database not found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def connect_postgres(database_url: str):
    """Connect to PostgreSQL database."""
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = False
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to PostgreSQL: {e}")
        sys.exit(1)


def get_table_names(sqlite_conn: sqlite3.Connection) -> list[str]:
    """Get all table names from SQLite database."""
    cursor = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    return [row[0] for row in cursor.fetchall()]


def copy_table(table_name: str, sqlite_conn: sqlite3.Connection, pg_conn) -> int:
    """Copy data from SQLite table to PostgreSQL table."""
    print(f"  Copying table: {table_name}")

    # Get all rows from SQLite
    sqlite_cursor = sqlite_conn.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cursor.fetchall()

    if not rows:
        print(f"    No data in {table_name}")
        return 0

    # Get column names
    columns = [description[0] for description in sqlite_cursor.description]

    # Prepare PostgreSQL insert
    placeholders = ', '.join(['%s'] * len(columns))
    column_names = ', '.join(columns)
    insert_query = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"

    # Insert rows into PostgreSQL
    pg_cursor = pg_conn.cursor()
    inserted = 0

    for row in rows:
        try:
            values = tuple(row[col] for col in columns)
            pg_cursor.execute(insert_query, values)
            inserted += 1
        except psycopg2.Error as e:
            print(f"    Warning: Failed to insert row into {table_name}: {e}")
            continue

    pg_cursor.close()
    print(f"    Copied {inserted} rows")
    return inserted


def verify_migration(sqlite_conn: sqlite3.Connection, pg_conn, tables: list[str]) -> bool:
    """Verify that row counts match between SQLite and PostgreSQL."""
    print("\nVerifying migration...")
    all_match = True

    for table in tables:
        sqlite_count = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        pg_cursor = pg_conn.cursor()
        pg_cursor.execute(f"SELECT COUNT(*) FROM {table}")
        pg_count = pg_cursor.fetchone()[0]
        pg_cursor.close()

        match = "✓" if sqlite_count == pg_count else "✗"
        print(f"  {match} {table}: SQLite={sqlite_count}, PostgreSQL={pg_count}")

        if sqlite_count != pg_count:
            all_match = False

    return all_match


def reset_sequences(pg_conn, tables: list[str]):
    """Reset PostgreSQL sequences after data import."""
    print("\nResetting PostgreSQL sequences...")
    pg_cursor = pg_conn.cursor()

    for table in tables:
        # Find columns with SERIAL type (have a sequence)
        pg_cursor.execute(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            AND column_default LIKE 'nextval%%'
        """, (table,))

        serial_columns = pg_cursor.fetchall()

        for col_row in serial_columns:
            col_name = col_row[0]
            sequence_name = f"{table}_{col_name}_seq"

            try:
                # Get max value from table
                pg_cursor.execute(f"SELECT MAX({col_name}) FROM {table}")
                max_val = pg_cursor.fetchone()[0]

                if max_val is not None:
                    # Set sequence to max + 1
                    pg_cursor.execute(f"SELECT setval('{sequence_name}', %s)", (max_val,))
                    print(f"  Reset {table}.{col_name} sequence to {max_val}")
            except psycopg2.Error as e:
                print(f"  Warning: Could not reset sequence for {table}.{col_name}: {e}")

    pg_cursor.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate shrimpicus data from SQLite to PostgreSQL")
    parser.add_argument("--sqlite", type=Path, required=True, help="Path to SQLite database file")
    parser.add_argument("--postgres", type=str, required=True, help="PostgreSQL connection URL")
    parser.add_argument("--skip-verification", action="store_true", help="Skip verification step")
    args = parser.parse_args()

    print("=" * 60)
    print("Shrimpicus Database Migration: SQLite → PostgreSQL")
    print("=" * 60)

    # Connect to databases
    print("\nConnecting to databases...")
    sqlite_conn = connect_sqlite(args.sqlite)
    pg_conn = connect_postgres(args.postgres)
    print("  ✓ Connected to both databases")

    # Initialize PostgreSQL schema using Database class
    print("\nInitializing PostgreSQL schema...")
    from shrimpicus.db import Database
    db = Database(database_url=args.postgres)
    db.init()
    print("  ✓ Schema initialized")

    # Get table names
    tables = get_table_names(sqlite_conn)
    print(f"\nFound {len(tables)} tables to migrate: {', '.join(tables)}")

    # Copy each table
    print("\nMigrating data...")
    total_rows = 0
    for table in tables:
        rows = copy_table(table, sqlite_conn, pg_conn)
        total_rows += rows

    # Commit transaction
    pg_conn.commit()
    print(f"\n✓ Migration complete! Total rows copied: {total_rows}")

    # Reset sequences
    reset_sequences(pg_conn, tables)
    pg_conn.commit()

    # Verify migration
    if not args.skip_verification:
        if verify_migration(sqlite_conn, pg_conn, tables):
            print("\n✓ Verification passed! All row counts match.")
        else:
            print("\n✗ Verification failed! Some row counts don't match.")
            print("  Review the output above and check for errors.")

    # Close connections
    sqlite_conn.close()
    pg_conn.close()

    print("\n" + "=" * 60)
    print("Migration complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Update your .env file to set DATABASE_URL to the PostgreSQL connection string")
    print("2. Restart the shrimpicus bot and web app")
    print("3. Test all features to ensure everything works")
    print("4. Keep the SQLite database as a backup until you're confident everything works")


if __name__ == "__main__":
    main()
