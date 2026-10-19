"""Scoped approved fact resolution. Private values live only in the local database."""
import json
from .database import now
from .runtime_policy import digest

VERSION = 'canonical-facts-1'


def schema(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS fact_memory(
      id TEXT PRIMARY KEY,field_key TEXT NOT NULL,value TEXT NOT NULL,normalized TEXT NOT NULL,
      source TEXT NOT NULL,source_version TEXT NOT NULL,source_timestamp TEXT NOT NULL,
      priority INTEGER NOT NULL,verification TEXT NOT NULL,scope TEXT NOT NULL,
      supersedes TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TRIGGER IF NOT EXISTS fact_memory_no_update BEFORE UPDATE ON fact_memory BEGIN SELECT RAISE(ABORT,'append_only'); END;
    CREATE TRIGGER IF NOT EXISTS fact_memory_no_delete BEFORE DELETE ON fact_memory BEGIN SELECT RAISE(ABORT,'append_only'); END;
    CREATE TABLE IF NOT EXISTS r2_reconciliations(id TEXT PRIMARY KEY,report TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TRIGGER IF NOT EXISTS r2_reconciliations_no_update BEFORE UPDATE ON r2_reconciliations BEGIN SELECT RAISE(ABORT,'append_only'); END;
    CREATE TRIGGER IF NOT EXISTS r2_reconciliations_no_delete BEFORE DELETE ON r2_reconciliations BEGIN SELECT RAISE(ABORT,'append_only'); END;
    CREATE TABLE IF NOT EXISTS draft_previews(id TEXT PRIMARY KEY,packet_id TEXT NOT NULL,
      contact_id TEXT NOT NULL,snapshot_hash TEXT NOT NULL,payload_hash TEXT NOT NULL,
      content TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TRIGGER IF NOT EXISTS draft_previews_no_update BEFORE UPDATE ON draft_previews BEGIN SELECT RAISE(ABORT,'append_only'); END;
    CREATE TRIGGER IF NOT EXISTS draft_previews_no_delete BEFORE DELETE ON draft_previews BEGIN SELECT RAISE(ABORT,'append_only'); END;
    CREATE TABLE IF NOT EXISTS draft_approvals(preview_id TEXT PRIMARY KEY REFERENCES draft_previews(id),approved_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS email_message_metadata(message_id TEXT PRIMARY KEY,sender TEXT,subject TEXT NOT NULL,received_at TEXT NOT NULL);
    ''')


def record(conn,key,value,*,source,version,priority=2,scope='shared',timestamp=None,supersede=False):
    if not str(value).strip() or not source or not scope:raise ValueError('fact_source_value_scope_required')
    normalized=' '.join(str(value).casefold().split())
    identifier=digest([VERSION,key,str(value),source,str(version),scope])
    previous=[]
    if supersede:
        previous=[r[0] for r in conn.execute('SELECT id FROM fact_memory WHERE field_key=? AND scope=?',(key,scope)) if r[0]!=identifier]
    conn.execute('INSERT OR IGNORE INTO fact_memory VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                 (identifier,key,str(value),normalized,source,str(version),timestamp or now(),priority,'VERIFIED',scope,json.dumps(previous),now()))
    return identifier


def resolve(candidates):
    """Same-precedence contradictory evidence remains a conflict, never concatenated."""
    if not candidates:return {'state':'UNKNOWN','value':None,'sources':[]}
    superseded={i for c in candidates for i in json.loads(c.get('supersedes','[]'))}
    active=[c for c in candidates if c.get('id') not in superseded]
    best=min(c['priority'] for c in active)
    selected=[c for c in active if c['priority']==best]
    values={c['normalized'] for c in selected}
    return {'state':'RESOLVED' if len(values)==1 else 'CONFLICT','value':selected[-1]['value'] if len(values)==1 else None,'sources':selected,'version':VERSION}


def projection(db,profile,document_facts,document_sources,company=''):
    candidates={}
    def add(key,value,priority,source,version):
        candidates.setdefault(key,[]).append(dict(value=str(value),normalized=' '.join(str(value).casefold().split()),priority=priority,source=source,source_version=str(version),scope='shared'))
    for key,value in document_facts.items():add(key,value,3,document_sources.get(key,{}),'approved-document')
    for key,value in profile.get('confirmed_facts',{}).items():add(key,value,2,profile.get('fact_provenance',{}).get(key,[]),profile.get('version'))
    for key,value in profile.get('approved_application_answers',{}).items():
        sources=profile.get('fact_provenance',{}).get(key,[])
        add(key,value,1 if any(s.get('source')=='user_confirmation' for s in sources) else 2,sources,profile.get('version'))
    with db.transaction() as conn:
        rows=[dict(r) for r in conn.execute("SELECT * FROM fact_memory WHERE scope='shared' OR scope=?",('employer:'+company.casefold().strip(),))]
    for row in rows:candidates.setdefault(row['field_key'],[]).append(row)
    return {key:resolve(values) for key,values in candidates.items()}
