import psycopg2
import psycopg2.extras
import click
import os
from flask import current_app, g

def get_db():
    if 'db' not in g:
        # Use DATABASE_URL from env or config
        db_url = current_app.config.get('DATABASE_URL') or os.environ.get('DATABASE_URL')
        if not db_url:
            raise RuntimeError("DATABASE_URL not set in environment or configuration")
            
        g.db = psycopg2.connect(db_url, cursor_factory=psycopg2.extras.DictCursor)
        # Compatibility helper to mimic sqlite3's commit behavior if needed
        # g.db.autocommit = True 

    return g.db

def close_db(e=None):
    db = g.pop('db', None)

    if db is not None:
        db.close()

def init_db():
    db = get_db()
    with current_app.open_resource('schema_pg.sql') as f:
        with db.cursor() as cur:
            cur.execute(f.read().decode('utf8'))
    db.commit()

@click.command('init-db')
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo('Initialized the PostgreSQL database.')

def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
