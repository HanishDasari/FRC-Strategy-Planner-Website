import mysql.connector
import click
import os
from flask import current_app, g
from urllib.parse import urlparse

def get_db():
    if 'db' not in g:
        db_url = current_app.config.get('DATABASE_URL') or os.environ.get('DATABASE_URL')
        if not db_url:
            raise RuntimeError("DATABASE_URL not set in environment or configuration")
            
        parsed = urlparse(db_url)
        # Assuming mysql://user:pass@host:port/db format
        g.db = mysql.connector.connect(
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port or 4000,
            database=parsed.path.lstrip('/'),
            autocommit=True
        )
        
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    with current_app.open_resource('schema_tidb.sql') as f:
        schema_sql = f.read().decode('utf8')
        with db.cursor() as cur:
            # mysql-connector's execute doesn't like multi statements unless multi=True
            for result in cur.execute(schema_sql, multi=True):
                pass
    db.commit()

@click.command('init-db')
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo('Initialized the TiDB database.')

def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
