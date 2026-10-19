"""Read-only projections; never classify, fetch mail, or mutate state on a GET."""
from urllib.parse import quote
import json


def inbox(db):
    with db.transaction() as conn:
        messages = [dict(row) for row in conn.execute("""SELECT m.*,p.category,p.tier,p.deadline,p.reason
            FROM email_message_metadata m LEFT JOIN message_priority p USING(message_id)
            ORDER BY COALESCE(p.tier,0) DESC,COALESCE(p.deadline,'9999'),m.received_at DESC,m.message_id""")]
    for item in messages:
        item['category'] = item['category'] or 'UNCLASSIFIED'
        item['gmail_url'] = 'https://mail.google.com/mail/u/0/#inbox/' + quote(item['message_id'], safe='')
    return {'items': messages, 'scope': 'retained_received_metadata_only'}


def runs(db):
    with db.transaction() as conn:
        items = [dict(row) for row in conn.execute('SELECT * FROM discovery_runs ORDER BY started_at DESC,id DESC LIMIT 50')]
        for item in items:
            item['metrics'] = json.loads(item['metrics'])
            item['sources'] = [dict(row) for row in conn.execute('SELECT source_id,status,started_at,finished_at,error FROM discovery_source_runs WHERE run_id=? ORDER BY source_id', (item['id'],))]
    return {'items': items, 'limit': 50}
