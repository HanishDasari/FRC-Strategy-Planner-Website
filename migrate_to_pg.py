import sqlite3
import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv

load_dotenv()

SQLITE_DB = 'frc_strategy.sqlite'
PG_DSN = os.environ.get('DATABASE_URL')

def migrate():
    if not PG_DSN:
        print("Error: DATABASE_URL not set in .env")
        return

    print(f"Connecting to SQLite: {SQLITE_DB}")
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    print(f"Connecting to PostgreSQL...")
    pg_conn = psycopg2.connect(PG_DSN)
    pg_cur = pg_conn.cursor()

    # Tables in order of dependency
    tables = [
        'teams',
        'users',
        'email_verifications',
        'password_resets',
        'matches',
        'match_alliances',
        'invites',
        'messages',
        'strategies',
        'drawings'
    ]

    try:
        for table in tables:
            print(f"Migrating table: {table}...")
            
            # Fetch from SQLite
            sqlite_cur.execute(f"SELECT * FROM {table}")
            rows = sqlite_cur.fetchall()
            
            if not rows:
                print(f"  No data in {table}, skipping.")
                continue

            # Prepare PG insert
            columns = rows[0].keys()
            placeholders = ', '.join(['%s'] * len(columns))
            cols_str = ', '.join(columns)
            query = f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

            # Insert into PG
            data = [tuple(row) for row in rows]
            pg_cur.executemany(query, data)
            print(f"  Successfully migrated {len(rows)} rows to {table}.")

        pg_conn.commit()
        print("\nMigration completed successfully!")
        
        # Reset serial sequences in PG
        print("Resetting sequences...")
        for table in tables:
            pg_cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), coalesce(max(id), 1)) FROM {table};")
        pg_conn.commit()
        print("Sequences reset.")

    except Exception as e:
        print(f"\nError during migration: {e}")
        pg_conn.rollback()
    finally:
        sqlite_conn.close()
        pg_conn.close()

if __name__ == "__main__":
    migrate()
