"""Postgres persistence using the same inbox/outbox contract as the local SQLite store."""
from contextlib import contextmanager
from .tickets import TicketStore

LOCK_ID=728194307

class Connection:
    def __init__(self,connection):self.connection=connection

    def execute(self,sql,parameters=()):
        # Only fixed internal SQL is adapted; customer values remain bound parameters.
        if sql=='BEGIN IMMEDIATE':
            return self.connection.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK_ID,))
        if sql.startswith('INSERT OR IGNORE INTO '):
            sql=sql.replace('INSERT OR IGNORE INTO ','INSERT INTO ',1)+' ON CONFLICT DO NOTHING'
        return self.connection.execute(sql.replace('?','%s'),parameters)

class PostgresTicketStore(TicketStore):
    def __init__(self,url):
        self.url=url
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for statement in SCHEMA:db.execute(statement)

    @contextmanager
    def connect(self):
        import psycopg
        from psycopg.rows import dict_row
        # No process-local connection pool; use the provider's pooled connection URL.
        with psycopg.connect(self.url,connect_timeout=10,row_factory=dict_row,prepare_threshold=None) as connection:
            connection.execute("SET LOCAL statement_timeout = '15s'")
            connection.execute("SET LOCAL lock_timeout = '5s'")
            yield Connection(connection)

SCHEMA=[
    '''CREATE TABLE IF NOT EXISTS tickets (
       id TEXT PRIMARY KEY,request_key TEXT UNIQUE NOT NULL,fingerprint TEXT NOT NULL,
       payload TEXT NOT NULL,status TEXT NOT NULL,plain_thread_id TEXT NOT NULL,
       created_at TEXT NOT NULL,updated_at TEXT NOT NULL,result TEXT,error TEXT)''',
    '''CREATE TABLE IF NOT EXISTS external_links (
       ticket_id TEXT NOT NULL REFERENCES tickets(id),provider TEXT NOT NULL,reference TEXT NOT NULL,
       PRIMARY KEY(ticket_id,provider))''',
    '''CREATE TABLE IF NOT EXISTS delivery_jobs (
       id BIGSERIAL PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES tickets(id),provider TEXT NOT NULL,
       stage TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
       error TEXT,result TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(ticket_id,provider,stage))''',
    '''CREATE TABLE IF NOT EXISTS ticket_events (
       sequence BIGSERIAL PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES tickets(id),
       type TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL)''',
    "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS plain_mode TEXT NOT NULL DEFAULT 'simulated'",
    *[f'ALTER TABLE tickets ADD COLUMN IF NOT EXISTS {name} TEXT' for name in
      ['plain_customer_id','original_payload','plain_summary','work_token','work_deadline']],
    'CREATE INDEX IF NOT EXISTS ticket_events_ticket_sequence ON ticket_events(ticket_id,sequence)',
    'CREATE INDEX IF NOT EXISTS delivery_jobs_ticket_status ON delivery_jobs(ticket_id,status)',
]
