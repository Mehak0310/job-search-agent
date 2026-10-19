"""Explicit local Gmail OAuth boundaries for received mail and unsent drafts."""
from __future__ import annotations
import base64
import hashlib
import json
import quopri
import re
from datetime import datetime,timezone
from email import policy
from email.parser import BytesParser
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from .m2d_models import EmailExportMessage

READONLY_SCOPE="https://www.googleapis.com/auth/gmail.readonly"
DRAFT_SCOPE="https://www.googleapis.com/auth/gmail.compose"  # M3 only; never requested here.

def gmail_query(start:str,end:str)->str:
    def epoch(value):return int(datetime.fromisoformat(value.replace("Z","+00:00")).timestamp())
    return f"after:{epoch(start)} before:{epoch(end)} -in:sent -in:drafts"

def _decode(value:str)->bytes:
    return base64.urlsafe_b64decode(value+"="*((4-len(value)%4)%4))

def message_from_api(raw:dict,cursor:str|None=None)->EmailExportMessage|None:
    labels=set(raw.get("labelIds") or [])
    if labels & {"SENT","DRAFT"}:return None
    payload=raw.get("payload") or {};headers={item.get("name","").casefold():item.get("value","") for item in payload.get("headers") or []}
    chunks=[]
    def walk(part):
        mime=part.get("mimeType","");data=(part.get("body") or {}).get("data")
        if data and mime in {"text/plain","text/html"}:
            content=_decode(data)
            part_headers={item.get('name','').casefold():item.get('value','') for item in part.get('headers') or []}
            # Gmail normally decodes transfer encoding before base64url wrapping.
            # Only decode an actually encoded export; blindly decoding corrupts
            # query values such as '=ab...' in already decoded alert URLs.
            if part_headers.get('content-transfer-encoding','').lower()=='quoted-printable' and re.search(br'=(?:\r?\n|3[Dd]|0[AaDd])',content):content=quopri.decodestring(content)
            charset='utf-8'
            from email.message import Message
            info=Message();info['Content-Type']=part_headers.get('content-type',mime)
            charset=info.get_content_charset() or charset
            try:chunks.append(content.decode(charset,'replace').encode('utf-8'))
            except LookupError:chunks.append(content.decode('utf-8','replace').encode('utf-8'))
        for child in part.get("parts") or []:walk(child)
    walk(payload)
    body=b"\n".join(chunks)
    # Gmail payload.parts already supplies MIME structure. Body text containing
    # 'Content-Type:' must never be reinterpreted as a new MIME envelope.
    received=datetime.fromtimestamp(int(raw["internalDate"])/1000,timezone.utc).isoformat().replace("+00:00","Z")
    address=parseaddr(headers.get('from',''))[1];domain=address.rsplit('@',1)[-1].lower() if '@' in address else None
    return EmailExportMessage(message_id=raw["id"],thread_id=raw.get("threadId"),received_at=received,labels=sorted(labels),mailbox="received",subject=headers.get("subject",""),sender_domain=domain,sender=headers.get('from'),body=body.decode("utf-8","replace"),cursor=cursor)

class GmailOAuthReader:
    def __init__(self,client_secret:Path,token:Path):self.client_secret=client_secret;self.token=token
    def status(self):
        return {"client_configured":self.client_secret.is_file(),"token_configured":self.token.is_file(),"scope":READONLY_SCOPE,"live_ready":self.client_secret.is_file() and self.token.is_file()}
    def service(self):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        credentials=Credentials.from_authorized_user_file(str(self.token),[READONLY_SCOPE])
        return build('gmail','v1',credentials=credentials,cache_discovery=False)

    def cached_message(self,service,message_id):
        # Mail bodies are immutable; list queries still determine current received
        # membership. Cache files are private beside the ignored OAuth token.
        folder=self.token.parent/'message-cache';folder.mkdir(parents=True,exist_ok=True)
        path=folder/(hashlib.sha256(message_id.encode()).hexdigest()+'.json')
        if path.is_file():return json.loads(path.read_text(encoding='utf-8'))
        raw=service.users().messages().get(userId='me',id=message_id,format='full').execute()
        temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(raw),encoding='utf-8');temporary.replace(path)
        return raw
    def authorize(self):
        if not self.client_secret.is_file():raise ValueError("gmail_client_secret_missing")
        try:from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:raise ValueError("gmail_dependencies_missing") from None
        credentials=InstalledAppFlow.from_client_secrets_file(str(self.client_secret),[READONLY_SCOPE]).run_local_server(host="127.0.0.1",port=0,open_browser=True)
        self.token.parent.mkdir(parents=True,exist_ok=True);self.token.write_text(credentials.to_json(),encoding="utf-8")
        return self.status()
    def read_interval(self,start:str,end:str,page_token:str|None=None,page_size:int=100):
        if not self.status()["live_ready"]:raise ValueError("gmail_local_authorization_required")
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:raise ValueError("gmail_dependencies_missing") from None
        service=self.service()
        response=service.users().messages().list(userId="me",q=gmail_query(start,end),maxResults=min(page_size,500),pageToken=page_token).execute();next_token=response.get("nextPageToken");messages=[]
        for item in response.get("messages") or []:
            raw=self.cached_message(service,item['id']);message=message_from_api(raw,next_token)
            if message:messages.append(message)
        return {"messages":messages,"next_page_token":next_token,"interval_start":start,"interval_end":end,"complete":not next_token}

def ingest_live_interval(engine,reader:GmailOAuthReader,start:str,end:str,*,max_pages:int=5,page_size:int=100):
    """Read and classify one immutable interval with an exact resumable page cursor."""
    from .policy_hooks import check
    check('research_worker','GMAIL_INTAKE')
    from .database import now
    from .m2d import GmailExportAdapter
    run_id=hashlib.sha256(f"gmail:{start}:{end}".encode()).hexdigest();stamp=now()
    with engine.db.transaction() as conn:
        row=conn.execute("SELECT * FROM gmail_live_runs WHERE run_id=?",(run_id,)).fetchone()
        if row and row["status"]=="COMPLETED":
            return {"run_id":run_id,"status":"COMPLETED","reused":True,"pages":row["pages"],"messages_seen":row["messages_seen"],"messages_classified":row["messages_classified"],"vacancies":row["vacancies"],"next_page_token":None}
        conn.execute("""INSERT INTO gmail_live_runs(run_id,interval_start,interval_end,status,started_at,updated_at)
          VALUES(?,?,?,'RUNNING',?,?) ON CONFLICT(run_id) DO UPDATE SET status='RUNNING',error_code=NULL,updated_at=excluded.updated_at""",(run_id,start,end,stamp,stamp))
        row=conn.execute("SELECT * FROM gmail_live_runs WHERE run_id=?",(run_id,)).fetchone();token=row["next_page_token"]
    pages=seen=classified=vacancies=0;adapter=GmailExportAdapter(engine)
    try:
        while pages<max_pages:
            result=reader.read_interval(start,end,token,page_size);messages=result["messages"]
            from .priority_queue import classify_message
            messages=sorted(messages,key=lambda m:(-classify_message(m)['tier'],classify_message(m)['deadline'] or '9999',m.received_at,m.message_id))
            intake=adapter.ingest(messages,import_id=run_id,limit=len(messages) or 1,interval_end=end)
            pages+=1;seen+=len(messages);classified+=intake["messages_classified"];vacancies+=intake["vacancies"];token=result["next_page_token"]
            with engine.db.transaction() as conn:
                conn.execute("UPDATE gmail_live_runs SET next_page_token=?,pages=pages+1,messages_seen=messages_seen+?,messages_classified=messages_classified+?,vacancies=vacancies+?,updated_at=? WHERE run_id=?",(token,len(messages),intake["messages_classified"],intake["vacancies"],now(),run_id))
            if not token:break
        status="COMPLETED" if not token else "PARTIAL"
        with engine.db.transaction() as conn:conn.execute("UPDATE gmail_live_runs SET status=?,completed_at=CASE WHEN ?='COMPLETED' THEN ? ELSE completed_at END,updated_at=? WHERE run_id=?",(status,status,now(),now(),run_id))
        from .m2d_models import CoverageStatus
        engine.record_coverage('gmail',CoverageStatus.EXHAUSTIVELY_SEARCHED if not token else CoverageStatus.PARTIALLY_SEARCHED,
            scope={'operation':'received_message_interval','start':start,'end':end,'run_id':run_id,'excludes':['SENT','DRAFT']},
            cursor={'next_page_token':token,'complete':not token},exhausted=not token)
        return {"run_id":run_id,"status":status,"reused":False,"pages":pages,"messages_seen":seen,"messages_classified":classified,"vacancies":vacancies,"next_page_token":token}
    except Exception as error:
        code=type(error).__name__
        with engine.db.transaction() as conn:conn.execute("UPDATE gmail_live_runs SET status='FAILED',error_code=?,updated_at=? WHERE run_id=?",(code,now(),run_id))
        raise

class GmailDraftAdapter:
    """Compose-scope adapter exposing draft creation only; there is no send method."""
    def __init__(self,client_secret:Path,token:Path):self.client_secret=client_secret;self.token=token
    def status(self):
        return {"client_configured":self.client_secret.is_file(),"token_configured":self.token.is_file(),"scope":DRAFT_SCOPE,"live_ready":self.client_secret.is_file() and self.token.is_file(),"warning":"gmail.compose permits draft management and sending; this application exposes draft creation only"}
    def authorize(self):
        if not self.client_secret.is_file():raise ValueError("gmail_client_secret_missing")
        try:from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:raise ValueError("gmail_dependencies_missing") from None
        credentials=InstalledAppFlow.from_client_secrets_file(str(self.client_secret),[READONLY_SCOPE,DRAFT_SCOPE]).run_local_server(host="127.0.0.1",port=0,open_browser=True)
        self.token.parent.mkdir(parents=True,exist_ok=True);self.token.write_text(credentials.to_json(),encoding="utf-8")
        return self.status()
    def create_draft(self,*,to:str,subject:str,text:str,html:str,thread_message_id:str|None=None,authorization_id:str|None=None):
        from .runtime_policy import require_external_write,draft_payload
        require_external_write('gmail_draft',root=self.token.parent.parent/'action-authorizations',
            authorization_id=authorization_id,target=to,
            payload_hash=draft_payload(to=to,subject=subject,text=text,html=html,thread_message_id=thread_message_id),consume=True)
        raise ValueError('r2_live_drafts_disabled_separate_post_verification_approval_required')
        if not self.status()["live_ready"]:raise ValueError("gmail_local_compose_authorization_required")
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:raise ValueError("gmail_dependencies_missing") from None
        credentials=Credentials.from_authorized_user_file(str(self.token),[READONLY_SCOPE,DRAFT_SCOPE]);service=build("gmail","v1",credentials=credentials,cache_discovery=False)
        message=EmailMessage();message["To"]=to;message["Subject"]=subject
        thread_id=None
        if thread_message_id:
            original=service.users().messages().get(userId="me",id=thread_message_id,format="metadata",metadataHeaders=["Message-ID"]).execute();thread_id=original.get("threadId")
            headers={item.get("name","").casefold():item.get("value","") for item in (original.get("payload") or {}).get("headers") or []}
            if headers.get("message-id"):message["In-Reply-To"]=headers["message-id"];message["References"]=headers["message-id"]
        message.set_content(text);message.add_alternative(html,subtype="html")
        body={"message":{"raw":base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")}}
        if thread_id:body["message"]["threadId"]=thread_id
        return service.users().drafts().create(userId="me",body=body).execute()
