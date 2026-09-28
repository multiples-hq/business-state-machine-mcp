"""Apply the ordered SQL migrations as the schema owner."""

import sys
from pathlib import Path

import psycopg


def migrate(dsn, through=None):
    """Apply pending migrations in filename order, stopping after `through` if given."""
    migration_dir = Path(__file__).resolve().parent / 'migrations'
    paths = sorted(migration_dir.glob('[0-9][0-9][0-9]_*.sql'))
    if not paths:
        raise RuntimeError('no database migrations found')
    if through is not None:
        names = [path.name for path in paths]
        if through not in names:
            raise ValueError(f'unknown migration: {through}')
        paths = paths[:names.index(through) + 1]
    applied_now = []
    with psycopg.connect(dsn) as connection:
        connection.execute('''
            CREATE TABLE IF NOT EXISTS spine.schema_migrations (
                filename text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
            )
        ''')
        already = {row[0] for row in connection.execute(
            'SELECT filename FROM spine.schema_migrations'
        )}
        for path in paths:
            if path.name in already:
                continue
            connection.execute(path.read_text())
            connection.execute(
                'INSERT INTO spine.schema_migrations (filename) VALUES (%s)', (path.name,)
            )
            applied_now.append(path.name)
    return applied_now


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: python postgres/migrate.py POSTGRES_DSN')
    for applied in migrate(sys.argv[1]):
        print(applied)
