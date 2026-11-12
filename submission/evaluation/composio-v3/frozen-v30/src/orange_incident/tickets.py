"""Persistent local demo inbox and job queue, separate from benchmark answers."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class Conflict(ValueError):
    pass


class TicketStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS tickets (
                    id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL,
                    fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
                    status TEXT NOT NULL, plain_thread_id TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    result TEXT, error TEXT
                );
                CREATE TABLE IF NOT EXISTS external_links (
                    ticket_id TEXT NOT NULL REFERENCES tickets(id),
                    provider TEXT NOT NULL, reference TEXT NOT NULL,
                    PRIMARY KEY(ticket_id,provider)
                );
                CREATE TABLE IF NOT EXISTS delivery_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id TEXT NOT NULL REFERENCES tickets(id),
                    provider TEXT NOT NULL, stage TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error TEXT, result TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(ticket_id,provider,stage)
                );
                CREATE TABLE IF NOT EXISTS ticket_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id TEXT NOT NULL REFERENCES tickets(id),
                    type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
            ''')
            columns={row['name'] for row in db.execute('PRAGMA table_info(tickets)')}
            if 'plain_mode' not in columns:
                db.execute("ALTER TABLE tickets ADD COLUMN plain_mode TEXT NOT NULL DEFAULT 'simulated'")
            if 'plain_customer_id' not in columns:
                db.execute('ALTER TABLE tickets ADD COLUMN plain_customer_id TEXT')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def event(db, ticket_id, kind, payload):
        db.execute('INSERT INTO ticket_events(ticket_id,type,payload,created_at) VALUES(?,?,?,?)',
                   (ticket_id, kind, json.dumps(payload), now()))

    def submit(self, payload: dict, request_key: str, plain_mode="simulated"):
        fingerprint = hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT id,fingerprint FROM tickets WHERE request_key=?',(request_key,)).fetchone()
            if existing:
                if existing['fingerprint'] != fingerprint:
                    raise Conflict('This request key was already used for a different complaint')
                return existing['id'], False
            ticket_id = str(uuid4())
            thread_id = 'mock-thread-' + ticket_id if plain_mode == 'simulated' else ''
            created = now()
            db.execute('INSERT INTO tickets(id,request_key,fingerprint,payload,status,plain_thread_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                       (ticket_id,request_key,fingerprint,json.dumps(payload),'queued' if plain_mode == 'simulated' else 'sending_to_plain',thread_id,created,created))
            db.execute('UPDATE tickets SET plain_mode=? WHERE id=?',(plain_mode,ticket_id))
            self.event(db,ticket_id,'complaint_received',{'title':payload['title']})
            if plain_mode == 'simulated':
                self.event(db,ticket_id,'plain_thread_created',{'mode':'simulated','thread_id':thread_id})
                self.event(db,ticket_id,'investigation_queued',{'source':'simulated_plain_event'})
            return ticket_id, True

    def get(self, ticket_id):
        with self.connect() as db:
            row=db.execute('SELECT * FROM tickets WHERE id=?',(ticket_id,)).fetchone()
            if not row:
                return None
            events=db.execute('SELECT sequence,type,payload,created_at FROM ticket_events WHERE ticket_id=? ORDER BY sequence',(ticket_id,)).fetchall()
            links=db.execute('SELECT provider,reference FROM external_links WHERE ticket_id=?',(ticket_id,)).fetchall()
            deliveries=db.execute('SELECT id,provider,stage,status,attempts,error FROM delivery_jobs WHERE ticket_id=? ORDER BY id',(ticket_id,)).fetchall()
        return {'id':row['id'],'complaint':json.loads(row['payload']),'status':row['status'],
                'plain':{'mode':row['plain_mode'],'thread_id':row['plain_thread_id'] or None},
                'created_at':row['created_at'],'updated_at':row['updated_at'],
                'result':json.loads(row['result']) if row['result'] else None,'error':row['error'],
                'events':[dict(e, payload=json.loads(e['payload'])) for e in events],
                'integrations':{r['provider']:json.loads(r['reference']) for r in links},
                'deliveries':[dict(r) for r in deliveries]}

    def summaries(self):
        with self.connect() as db:
            rows=db.execute("SELECT id,payload,status,created_at,updated_at,(SELECT COUNT(*) FROM ticket_events e WHERE e.ticket_id=tickets.id) event_count FROM tickets ORDER BY created_at DESC LIMIT 100").fetchall()
        return [{'id':r['id'],'complaint':json.loads(r['payload']),'status':r['status'],'created_at':r['created_at'],'updated_at':r['updated_at'],'event_count':r['event_count']} for r in rows]

    def list(self):
        with self.connect() as db:
            ids=[r['id'] for r in db.execute('SELECT id FROM tickets ORDER BY created_at DESC LIMIT 100')]
        return [self.get(ticket_id) for ticket_id in ids]

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT id FROM tickets WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if not row:
                return None
            ticket_id=row['id']
            db.execute("UPDATE tickets SET status='investigating',updated_at=? WHERE id=?",(now(),ticket_id))
            self.event(db,ticket_id,'investigation_started',{})
        return self.get(ticket_id)

    def finish(self,ticket_id,result=None,error=None):
        status='failed' if error else 'needs_review'
        with self.connect() as db:
            db.execute('UPDATE tickets SET status=?,result=?,error=?,updated_at=? WHERE id=?',
                       (status,json.dumps(result) if result else None,error,now(),ticket_id))
            self.event(db,ticket_id,'investigation_failed' if error else 'report_ready',{'error':error} if error else {'outcome':result['report']['outcome']})
            if not error:
                self.event(db,ticket_id,'response_drafted',{'sent':False})

    def mark_interrupted(self):
        with self.connect() as db:
            uncertain=db.execute("SELECT id FROM tickets WHERE status='sending_to_plain'").fetchall()
            for row in uncertain:
                db.execute("UPDATE tickets SET status='plain_attention_required',error=?,updated_at=? WHERE id=?",
                           ('Plain delivery was interrupted; inspect Plain before resubmitting.',now(),row['id']))
                self.event(db,row['id'],'plain_attention_required',{'blind_retry_allowed':False})
            rows=db.execute("SELECT id FROM tickets WHERE status='investigating'").fetchall()
            for row in rows:
                db.execute("UPDATE tickets SET status='failed',error=?,updated_at=? WHERE id=?",('Worker stopped before completion; retry explicitly',now(),row['id']))
                self.event(db,row['id'],'investigation_interrupted',{})

    def retry(self,ticket_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status FROM tickets WHERE id=?',(ticket_id,)).fetchone()
            if not row:
                raise KeyError(ticket_id)
            if row['status'] != 'failed':
                raise Conflict('Only failed investigations can be retried')
            db.execute("UPDATE tickets SET status='queued',error=NULL,result=NULL,updated_at=? WHERE id=?",(now(),ticket_id))
            self.event(db,ticket_id,'investigation_queued',{'source':'explicit_retry'})


    def reinvestigate(self,ticket_id,request_key,reason):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status,result FROM tickets WHERE id=?',(ticket_id,)).fetchone()
            if not row:raise KeyError(ticket_id)
            requests=db.execute("SELECT payload FROM ticket_events WHERE ticket_id=? AND type='investigation_queued'",(ticket_id,)).fetchall()
            for item in requests:
                payload=json.loads(item['payload'])
                if payload.get('request_key')==request_key:
                    if payload.get('reason')!=reason:raise Conflict('Reinvestigation key already used with different content')
                    return False
            if row['status'] not in ('needs_review','reviewed','changes_requested','failed'):
                raise Conflict('Wait for the current investigation before requesting another')
            self.event(db,ticket_id,'previous_investigation_saved',{'result':json.loads(row['result']) if row['result'] else None,'status':row['status']})
            db.execute("UPDATE tickets SET status='queued',error=NULL,result=NULL,updated_at=? WHERE id=?",(now(),ticket_id))
            self.event(db,ticket_id,'investigation_queued',{'source':'explicit_reinvestigation','request_key':request_key,'reason':reason})
        return True

    def plain_created(self,ticket_id,thread_id,customer_id):
        with self.connect() as db:
            db.execute("UPDATE tickets SET status='awaiting_plain_read',plain_thread_id=?,plain_customer_id=?,updated_at=? WHERE id=?",
                       (thread_id,customer_id,now(),ticket_id))
            self.event(db,ticket_id,'plain_thread_created',{'mode':'live','thread_id':thread_id})

    def plain_confirmed(self,ticket_id,thread):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM tickets WHERE id=?',(ticket_id,)).fetchone()
            if not row or row['status'] != 'awaiting_plain_read':
                return False
            if thread.get('externalId') != ticket_id or thread.get('id') != row['plain_thread_id']:
                raise Conflict('Plain thread correlation mismatch')
            payload=json.loads(row['payload'])
            payload['title']=thread['title']
            payload['description']=thread.get('description') or payload['description']
            db.execute("UPDATE tickets SET status='queued',payload=?,updated_at=? WHERE id=?",(json.dumps(payload),now(),ticket_id))
            self.event(db,ticket_id,'plain_thread_read',{'thread_id':thread['id'],'mode':'live'})
            self.event(db,ticket_id,'investigation_queued',{'source':'plain_api_read'})
        return True

    def pending_plain(self):
        with self.connect() as db:
            row=db.execute("SELECT id FROM tickets WHERE status='awaiting_plain_read' ORDER BY created_at LIMIT 1").fetchone()
        return self.get(row['id']) if row else None

    def plain_failed(self,ticket_id):
        with self.connect() as db:
            db.execute("UPDATE tickets SET status='plain_attention_required',error=?,updated_at=? WHERE id=?",
                       ('Plain delivery or read could not be confirmed. Inspect Plain before resubmitting.',now(),ticket_id))
            self.event(db,ticket_id,'plain_attention_required',{'blind_retry_allowed':False})


    def review(self,ticket_id,verdict,notes,reviewer='human'):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status FROM tickets WHERE id=?',(ticket_id,)).fetchone()
            if not row:
                raise KeyError(ticket_id)
            if row['status'] not in ('needs_review','reviewed','changes_requested'):
                raise Conflict('A completed investigation is required before review')
            status='reviewed' if verdict=='accepted' else 'changes_requested'
            db.execute('UPDATE tickets SET status=?,updated_at=? WHERE id=?',(status,now(),ticket_id))
            self.event(db,ticket_id,'review_recorded',{'verdict':verdict,'notes':notes,'reviewer':reviewer,'response_sent':False,
                'knowledge_updated':False})


    def enqueue_delivery(self,ticket_id,provider,stage):
        with self.connect() as db:
            created=db.execute('INSERT OR IGNORE INTO delivery_jobs(ticket_id,provider,stage,created_at,updated_at) VALUES(?,?,?,?,?)',
                               (ticket_id,provider,stage,now(),now())).rowcount
            if created:
                self.event(db,ticket_id,'delivery_queued',{'provider':provider,'stage':stage})

    def claim_delivery(self,providers):
        if not providers:
            return None
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            placeholders=','.join('?' for _ in providers)
            row=db.execute(f"SELECT * FROM delivery_jobs WHERE status='pending' AND provider IN ({placeholders}) ORDER BY id LIMIT 1",tuple(providers)).fetchone()
            if row is None:
                return None
            db.execute("UPDATE delivery_jobs SET status='sending',attempts=attempts+1,updated_at=? WHERE id=?",(now(),row['id']))
            return dict(row)

    def delivery_reference(self,ticket_id,provider):
        with self.connect() as db:
            row=db.execute('SELECT reference FROM external_links WHERE ticket_id=? AND provider=?',(ticket_id,provider)).fetchone()
        return json.loads(row['reference']) if row else None

    def delivery_complete(self,job,reference):
        with self.connect() as db:
            db.execute('UPDATE delivery_jobs SET status=?,result=?,error=NULL,updated_at=? WHERE id=?',
                       ('complete',json.dumps(reference),now(),job['id']))
            if job['stage']=='intake':
                db.execute('INSERT INTO external_links(ticket_id,provider,reference) VALUES(?,?,?) ON CONFLICT(ticket_id,provider) DO UPDATE SET reference=excluded.reference',
                           (job['ticket_id'],job['provider'],json.dumps(reference)))
                db.execute("UPDATE delivery_jobs SET status='pending',error=NULL,updated_at=? WHERE ticket_id=? AND provider=? AND status='blocked'",
                           (now(),job['ticket_id'],job['provider']))
            self.event(db,job['ticket_id'],'delivery_completed',{'provider':job['provider'],'stage':job['stage']})

    def delivery_failed(self,job,status,error):
        with self.connect() as db:
            db.execute('UPDATE delivery_jobs SET status=?,error=?,updated_at=? WHERE id=?',(status,error,now(),job['id']))
            self.event(db,job['ticket_id'],'delivery_attention_required' if status=='attention_required' else 'delivery_failed',
                       {'provider':job['provider'],'stage':job['stage'],'status':status,'error':error})

    def mark_deliveries_interrupted(self):
        with self.connect() as db:
            rows=db.execute("SELECT * FROM delivery_jobs WHERE status='sending'").fetchall()
            for row in rows:
                db.execute("UPDATE delivery_jobs SET status='attention_required',error=?,updated_at=? WHERE id=?",
                           ('Worker stopped during delivery. Inspect the destination before retrying.',now(),row['id']))
                self.event(db,row['ticket_id'],'delivery_attention_required',{'provider':row['provider'],'stage':row['stage']})

    def retry_delivery(self,job_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM delivery_jobs WHERE id=?',(job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row['status']!='failed':
                raise Conflict('Only definitively failed deliveries can be retried; uncertain deliveries require reconciliation')
            db.execute("UPDATE delivery_jobs SET status='pending',error=NULL,updated_at=? WHERE id=?",(now(),job_id))
            self.event(db,row['ticket_id'],'delivery_requeued',{'provider':row['provider'],'stage':row['stage']})
