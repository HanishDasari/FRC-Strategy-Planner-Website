import sqlite3
import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv

load_dotenv()

SQLITE_DB = 'frc_strategy.sqlite'
PG_DSN = os.environ.get('DATABASE_URL')

def migrate_v3():
    if not PG_DSN:
        print("Error: DATABASE_URL not set in .env")
        return

    print(f"Connecting to SQLite: {SQLITE_DB}")
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    print(f"Connecting to PostgreSQL...")
    pg_conn = psycopg2.connect(PG_DSN)
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    team_id_map = {}
    user_id_map = {}
    match_id_map = {}

    try:
        # 1. Migrating TEAMS
        print("Migrating teams...")
        sqlite_cur.execute("SELECT * FROM teams")
        for row in sqlite_cur.fetchall():
            pg_cur.execute(
                "INSERT INTO teams (team_number, team_name) VALUES (%s, %s) "
                "ON CONFLICT (team_number) DO UPDATE SET team_name = EXCLUDED.team_name RETURNING id",
                (row['team_number'], row['team_name'])
            )
            team_id_map[row['id']] = pg_cur.fetchone()['id']

        # 2. Migrating USERS
        print("Migrating users...")
        sqlite_cur.execute("SELECT * FROM users")
        for row in sqlite_cur.fetchall():
            d = dict(row)
            old_id = d.pop('id')
            d['team_id'] = team_id_map.get(d['team_id'], d['team_id'])
            
            cols = d.keys()
            query = f"INSERT INTO users ({', '.join(cols)}) VALUES ({', '.join(['%s']*len(cols))}) " \
                    f"ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name RETURNING id"
            pg_cur.execute(query, list(d.values()))
            user_id_map[old_id] = pg_cur.fetchone()['id']

        # 3. Migrating MATCHES
        print("Migrating matches...")
        sqlite_cur.execute("SELECT * FROM matches")
        for row in sqlite_cur.fetchall():
            d = dict(row)
            old_id = d.pop('id')
            d['creator_team_id'] = team_id_map.get(d['creator_team_id'], d['creator_team_id'])
            
            cols = d.keys()
            # No unique constraint on matches except ID, so we just insert and get a new ID
            query = f"INSERT INTO matches ({', '.join(cols)}) VALUES ({', '.join(['%s']*len(cols))}) RETURNING id"
            pg_cur.execute(query, list(d.values()))
            match_id_map[old_id] = pg_cur.fetchone()['id']

        # 4. Migrating OTHER tables
        tables = [
            ('email_verifications', ['user_id']),
            ('password_resets', ['user_id']),
            ('match_alliances', ['team_id', 'match_id']),
            ('invites', ['from_team_id', 'to_team_id', 'match_id']),
            ('messages', ['sender_user_id', 'sender_team_id', 'match_id']),
            ('strategies', ['match_id']),
            ('drawings', ['match_id'])
        ]
        
        team_cols = ['team_id', 'creator_team_id', 'from_team_id', 'to_team_id', 'sender_team_id']
        user_cols = ['user_id', 'sender_user_id']
        match_cols = ['match_id']

        for table, _ in tables:
            print(f"Migrating {table}...")
            sqlite_cur.execute(f"SELECT * FROM {table}")
            for row in sqlite_cur.fetchall():
                d = dict(row)
                if 'id' in d: d.pop('id')
                
                # Apply maps
                for col in d.keys():
                    if col in team_cols:
                        d[col] = team_id_map.get(d[col], d[col])
                    if col in user_cols:
                        d[col] = user_id_map.get(d[col], d[col])
                    if col in match_cols:
                        d[col] = match_id_map.get(d[col], d[col])
                
                cols = d.keys()
                query = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s']*len(cols))}) ON CONFLICT DO NOTHING"
                pg_cur.execute(query, list(d.values()))

        pg_conn.commit()
        print("Migration V3 successful!")

    except Exception as e:
        print(f"Migration failed: {e}")
        pg_conn.rollback()
    finally:
        sqlite_conn.close()
        pg_conn.close()

if __name__ == "__main__":
    migrate_v3()
