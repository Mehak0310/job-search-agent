"""Deterministic, local M3 application preparation and draft journal."""
from __future__ import annotations
import hashlib,html,json,re,sqlite3,uuid
from pathlib import Path
from .database import now
from .m3_models import ContactInput,DraftRequest,EmployerQuestion,PacketEdit,PacketStatus
from .candidate import display_skill
from .private_config import document_for_role

GENERATOR="jd-grounded-preparation-v2"
RED='style="color:#c00;font-weight:bold"'

def _json(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def _hash(value):return hashlib.sha256(_json(value).encode()).hexdigest()

class M3Engine:
    def __init__(self,db,manifest_path:Path|None=None):
        self.db=db;self.manifest_path=manifest_path or db.path.parent/"documents"/"manifest.json"

    def _documents(self):
        if not self.manifest_path.is_file():return {}
        try:data=json.loads(self.manifest_path.read_text("utf-8"))
        except (OSError,json.JSONDecodeError):return {}
        entries=data.get("documents",data if isinstance(data,list) else [])
        return {item.get("canonical_name"):item for item in entries if isinstance(item,dict) and item.get("canonical_name")}

    def _profile(self,conn):
        row=conn.execute("SELECT version,config FROM candidate_profiles_v2 ORDER BY version DESC LIMIT 1").fetchone()
        if row:return row["version"],json.loads(row["config"])
        row=conn.execute("SELECT config FROM candidate_profile WHERE id=1").fetchone();return 1,json.loads(row["config"])

    def _job(self,conn,job_key):
        return conn.execute("""SELECT s.*,j.company,j.title,j.location,j.work_mode,j.description,j.skills,
          j.required_skills,j.preferred_skills,j.required_experience_min,j.required_experience_max,
          j.canonical_application_url,j.application_url,j.content_hash,j.updated_at AS vacancy_updated_at,j.match_score,j.match_detail
          FROM job_operational_state s JOIN jobs j ON j.id=s.job_id WHERE s.job_key=?""",(job_key,)).fetchone()

    @staticmethod
    def _evidence(profile,job):
        skills=set(json.loads(job["skills"] or "[]"));required=set(json.loads(job["required_skills"] or "[]"));preferred=set(json.loads(job["preferred_skills"] or "[]"))
        approved=set(profile.get("employment_skills",[]))|set(profile.get("project_skills",[]))|set(profile.get("professional_skills",[]));years=profile.get("technology_years",{})
        assessed=required or skills;matched=sorted(assessed & approved);evidence=[]
        for skill in matched[:3]:
            duration=years.get(skill);scope=f", including {duration:g} years recorded in the approved profile" if duration is not None else " in the approved profile"
            evidence.append(f"The vacancy calls for {display_skill(skill)}; the profile provides matching {display_skill(skill)} evidence{scope}.")
        total=profile.get("total_experience_years");minimum=job["required_experience_min"]
        # Overall tenure cannot prove a technology-specific or relevant-work minimum.
        gaps=[]
        for skill in sorted(required-approved):
            if skill=="azure" and "azure fundamentals" in approved:gaps.append("Azure expertise is required; the approved evidence is limited to Azure fundamentals.")
            else:gaps.append(f"Required capability not evidenced in the approved profile: {display_skill(skill)}.")
        for skill in sorted(preferred-approved):gaps.append(f"Preferred capability not evidenced: {display_skill(skill)}.")
        if not required:gaps.insert(0,"Mandatory requirements have not yet been structured from the vacancy.")
        return evidence[:4] or ["The vacancy requirements still need structured assessment before a specific profile match can be stated."],gaps[:8]

    def prepare(self,job_key,force=False):
        stamp=now()
        with self.db.transaction() as conn:
            job=self._job(conn,job_key)
            if not job:raise ValueError("job_not_found")
            if not job['company'] or not job['title']:raise ValueError('Official employer and role must be verified before preparing application text.')
            profile_version,profile=self._profile(conn);documents=self._documents()
            verified_evidence=[dict(row) for row in conn.execute("SELECT kind,state,factual,inference,evidence_url,verified_at FROM job_evidence WHERE job_key=? ORDER BY kind,verified_at DESC",(job_key,)).fetchall()]
            portal=next((json.loads(item['factual']) for item in verified_evidence if item['kind']=='portal_form' and item['state']=='PASS'),None)
            document_versions={name:{"version":item.get("version"),"sha256":item.get("sha256"),"status":item.get("status")} for name,item in documents.items()}
            missing=list(json.loads(job["missing_facts"] or "[]"))
            resume=document_for_role(list(documents.values()),'resume',self.db.path.parent)
            bank=document_for_role(list(documents.values()),'answer_bank',self.db.path.parent)
            card=document_for_role(list(documents.values()),'profile_card',self.db.path.parent)
            resume_name=resume['canonical_name'] if resume else 'Resume.pdf'
            card_name=card['canonical_name'] if card else 'Profile_Card.png'
            if not resume or 'missing' in str(resume.get('status','')).casefold():missing.append('canonical_resume_path')
            if not bank or 'missing' in str(bank.get('status','')).casefold():missing.append('private_answer_bank_path')
            candidate_name=profile.get('candidate_name','').strip()
            if not candidate_name:missing.append('candidate_name')
            incompatible=job["readiness"]=="EXCLUDED" or job["lifecycle"]=="CLOSED"
            fit,gaps=self._evidence(profile,job);company=job["company"];title=job["title"]
            subject=f"Application for {title}"+(f" - {candidate_name}" if candidate_name else "")
            intro=f"I am writing to express interest in the {title} role at {company}."
            requirement_facts=[item["factual"] for item in verified_evidence if item["kind"]=="mandatory_requirements" and item["state"]=="PASS" and item["factual"]]
            if requirement_facts:
                fit.append("Verified role requirements: "+requirement_facts[0]);gaps=[gap for gap in gaps if gap!="Mandatory requirements have not yet been structured from the vacancy."]
            from .application_answers import tailored
            role_text,role_inputs=tailored(profile,job['description'],title,company)
            evidence_text=role_text
            body=f"{intro}\n\n{evidence_text}\n\nI would welcome the opportunity to discuss the role and can provide any additional information required.\n\n<profile card here>\n\nRegards,\n{candidate_name or '[name required]'}"
            instructions=f"ATTACH: {resume_name}.\nINSERT: {card_name} at the marker.\nREMOVE: all red instructions and markers before sending."
            email_text=body+"\n\nPREPARATION INSTRUCTIONS:\n"+instructions
            email_html="".join((f"<p>{html.escape(intro)}</p>",f"<p>{html.escape(evidence_text)}</p>","<p>I would welcome the opportunity to discuss the role and can provide any additional information required.</p>",f"<p {RED}>&lt;profile card here&gt;</p>",f"<p>Regards,<br>{html.escape(candidate_name or '[name required]')}</p>",f"<p {RED}>ATTACH: {html.escape(resume_name)}.<br>INSERT: {html.escape(card_name)} at the marker.<br>REMOVE: all red instructions and markers before sending.</p>"))
            supporting=f"I am interested in the {title} position at {company}. {evidence_text} I would value the opportunity to contribute and discuss how my experience fits the role."
            if portal:
                approved=set(profile.get('professional_skills',[]));years=profile.get('technology_years',{})
                supported=[f"{display_skill(skill)} ({years[skill]:g} years recorded)" for skill in ('angular','react','typescript') if skill in approved and skill in years]
                supporting=f"I am interested in the {title} role at {company}. My professional experience includes {', '.join(supported)}."
                if {'ui architecture','mentoring','testing'}<=approved:supporting+=' My approved experience also covers UI architecture, mentoring and testing.'
                if {'rag','llm inference/integration','github copilot agent'}<=approved:supporting+=' My professional AI application experience includes RAG, LLM integration and AI-assisted engineering workflows.'
                supporting+=' I would welcome a discussion of how this experience fits your team.'
                missing+=portal.get('missing_personal_answers',[])
                gaps+=portal.get('outstanding_agent_checks',[])
            supporting=role_text
            vacancy_version=job["content_hash"] or job["vacancy_updated_at"] or "unknown"
            payload={"subject":subject,"email_text":email_text,"email_html":email_html,"supporting_statement":supporting,"fit":fit,"gaps":gaps,"profile":profile_version,"vacancy":vacancy_version,"documents":document_versions,"missing":sorted(set(missing))}
            content_hash=_hash(payload);existing=conn.execute("SELECT * FROM application_packets WHERE job_key=?",(job_key,)).fetchone()
            if existing:
                current=conn.execute("SELECT user_edited FROM application_packet_versions WHERE packet_id=? AND version=?",(existing["packet_id"],existing["current_version"])).fetchone()
                if current and current["user_edited"] and not force:return self.get(existing["packet_id"])
            if existing and existing["content_hash"]==content_hash and not force:return self.get(existing["packet_id"])
            packet_id=existing["packet_id"] if existing else uuid.uuid4().hex;version=(existing["current_version"]+1) if existing else 1
            status=PacketStatus.BLOCKED_INCOMPATIBLE if incompatible else PacketStatus.NEEDS_USER_INFORMATION if missing else PacketStatus.TEXT_PREPARED if portal else PacketStatus.CONTACT_VERIFICATION_PENDING
            required=portal.get('required_documents',[resume_name]) if portal else [resume_name,card_name]
            answer_keys=("notice_period","expected_compensation","current_compensation","shift_preference")
            provenance={"job_key":job_key,"vacancy_url":job["canonical_application_url"] or job["application_url"],"profile_version":profile_version,"document_versions":document_versions,"profile_fact_sources":{key:profile.get("fact_provenance",{}).get(key,[]) for key in answer_keys},"job_evidence":[{"kind":item["kind"],"state":item["state"],"evidence_url":item["evidence_url"],"verified_at":item["verified_at"]} for item in verified_evidence],"generated_at":stamp,"template":GENERATOR}
            provenance['role_answer_inputs']=role_inputs
            conn.execute("""INSERT INTO application_packets VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(packet_id) DO UPDATE SET status=excluded.status,current_version=excluded.current_version,profile_version=excluded.profile_version,vacancy_version=excluded.vacancy_version,document_versions=excluded.document_versions,missing_information=excluded.missing_information,required_documents=excluded.required_documents,manual_next_action=excluded.manual_next_action,content_hash=excluded.content_hash,updated_at=excluded.updated_at""",(packet_id,job_key,job["job_id"],status.value,version,profile_version,vacancy_version,_json(document_versions),_json(sorted(set(missing))),_json(required),"Review text and missing facts; verify a relevant recipient before creating an unsent Gmail draft.",content_hash,existing["created_at"] if existing else stamp,stamp))
            if portal:
                conn.execute('UPDATE application_packets SET manual_next_action=? WHERE packet_id=?',('Review inspected portal questions and supporting statement; confirm outstanding eligibility before any external filling.',packet_id))
                provenance['portal_inspection']=portal
            conn.execute("INSERT INTO application_packet_versions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(packet_id,version,subject,email_html,email_text,supporting,_json(fit),_json(gaps),_json(provenance),GENERATOR,0,stamp))
            self.db.audit(conn,"APPLICATION_PACKET_PREPARED",{"packet_id":packet_id,"version":version,"generator":GENERATOR},job["job_id"])
        return self.get(packet_id)

    def prepare_queue(self):
        from .priority_queue import refresh,candidates
        refresh(self.db)
        with self.db.transaction() as conn:keys=[conn.execute('SELECT job_key FROM job_operational_state WHERE job_id=?',(r['job_id'],)).fetchone()[0] for r in candidates(self.db,5)]
        result={"selected":len(keys),"prepared":0,"unchanged":0,"failed":[]}
        for key in keys:
            before=self.by_job(key);packet=self.prepare(key);result["unchanged" if before and before["current_version"]==packet["current_version"] else "prepared"]+=1
        from .automatic_drafts import process
        result['automatic_drafts']=process(self.db,engine=self)
        return result

    def get(self,packet_id):
        with self.db.transaction() as conn:
            packet=conn.execute("SELECT p.*,j.company,j.title,j.canonical_application_url,j.application_url FROM application_packets p JOIN jobs j ON j.id=p.job_id WHERE packet_id=?",(packet_id,)).fetchone()
            if not packet:return None
            version=conn.execute("SELECT * FROM application_packet_versions WHERE packet_id=? AND version=?",(packet_id,packet["current_version"])).fetchone()
            questions=[dict(r) for r in conn.execute("SELECT q.*,a.answer,a.status AS answer_status,a.provenance AS answer_provenance FROM application_questions q LEFT JOIN application_answers a ON a.question_id=q.question_id AND a.version=(SELECT max(version) FROM application_answers WHERE question_id=q.question_id) WHERE q.packet_id=? ORDER BY q.created_at,q.question_id",(packet_id,))]
            contacts=[dict(r) for r in conn.execute("SELECT * FROM contact_evidence WHERE job_key=? ORDER BY updated_at DESC",(packet["job_key"],))]
            operations=[dict(r) for r in conn.execute("SELECT * FROM gmail_draft_operations WHERE packet_id=? ORDER BY created_at DESC",(packet_id,))]
            from .application_state import submission_projection
            submission=submission_projection(conn,packet['job_id'])
            from .requirements import assess_requirements
            _,current_profile=self._profile(conn)
            current_job=dict(conn.execute('SELECT * FROM jobs WHERE id=?',(packet['job_id'],)).fetchone())
            assessment=assess_requirements(current_profile,current_job,[dict(e) for e in conn.execute('SELECT * FROM job_evidence WHERE job_key=?',(packet['job_key'],))])
        out=dict(packet);out["version_data"]=dict(version);out["questions"]=questions;out["contacts"]=contacts;out["draft_operations"]=operations
        out.update(submission)
        out['requirement_assessment']=assessment
        for field in ("document_versions","missing_information","required_documents"):out[field]=json.loads(out[field])
        for field in ("fit_summary","gaps","provenance"):out["version_data"][field]=json.loads(out["version_data"][field])
        return out

    def by_job(self,job_key):
        with self.db.transaction() as conn:row=conn.execute("SELECT packet_id FROM application_packets WHERE job_key=?",(job_key,)).fetchone()
        return self.get(row[0]) if row else None

    def list(self,status=None,include_history=False):
        sql="""SELECT p.packet_id,p.job_key,p.status,p.current_version,p.missing_information,p.updated_at,j.company,j.title,j.id AS job_id,j.canonical_application_url,j.application_url,v.fit_summary,v.gaps FROM application_packets p JOIN jobs j ON j.id=p.job_id JOIN application_packet_versions v ON v.packet_id=p.packet_id AND v.version=p.current_version"""
        with self.db.transaction() as conn:rows=conn.execute(sql+(" WHERE p.status=?" if status else "")+" ORDER BY p.updated_at DESC,p.packet_id",(status,) if status else ()).fetchall()
        from .review_queue import hidden_job_ids
        hidden=set() if include_history else hidden_job_ids(self.db)
        return [{**dict(r),"missing_information":json.loads(r["missing_information"]),"fit_summary":json.loads(r["fit_summary"]),"gaps":json.loads(r["gaps"])} for r in rows if r["job_id"] not in hidden]

    def edit(self,packet_id,data:PacketEdit):
        stamp=now()
        with self.db.transaction() as conn:
            packet=conn.execute("SELECT * FROM application_packets WHERE packet_id=?",(packet_id,)).fetchone()
            if not packet:raise ValueError("packet_not_found")
            previous=conn.execute("SELECT * FROM application_packet_versions WHERE packet_id=? AND version=?",(packet_id,packet["current_version"])).fetchone();version=packet["current_version"]+1
            provenance=json.loads(previous["provenance"]);provenance.update({"edited_at":stamp,"based_on_version":packet["current_version"]})
            conn.execute("INSERT INTO application_packet_versions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(packet_id,version,data.subject,data.email_html,data.email_text,data.supporting_statement,previous["fit_summary"],previous["gaps"],_json(provenance),"user-edit",1,stamp))
            conn.execute("UPDATE application_packets SET current_version=?,content_hash=?,updated_at=? WHERE packet_id=?",(version,_hash(data.model_dump()),stamp,packet_id))
        return self.get(packet_id)

    def add_question(self,packet_id,data:EmployerQuestion):
        qid=hashlib.sha256(f"{packet_id}:{data.source}:{data.source_ref}".encode()).hexdigest();stamp=now()
        with self.db.transaction() as conn:
            packet=conn.execute("SELECT profile_version FROM application_packets WHERE packet_id=?",(packet_id,)).fetchone()
            if not packet:raise ValueError("packet_not_found")
            conn.execute("INSERT OR IGNORE INTO application_questions VALUES(?,?,?,?,?,?,?,?)",(qid,packet_id,data.question,data.source,data.source_ref,data.character_limit,data.field_kind,stamp))
            existing=conn.execute("SELECT 1 FROM application_answers WHERE question_id=?",(qid,)).fetchone()
            if not existing:
                from .application_answers import approved_facts
                profile,facts,_,_=approved_facts(self.db);answer=None;fact_key=None
                if data.field_kind=="NOTICE":fact_key="notice_period";answer=facts.get(fact_key)
                elif data.field_kind=="SALARY":fact_key="expected_compensation";answer=facts.get(fact_key)
                from .application_answers import answer as resolve_answer
                job=conn.execute('SELECT j.* FROM application_packets p JOIN jobs j ON j.id=p.job_id WHERE p.packet_id=?',(packet_id,)).fetchone()
                mapped,mapped_key=resolve_answer({'label':data.question,'type':'text','required':True,'max_length':data.character_limit or -1},facts,profile,job['description'],job['title'],job['company'],'india' in (job['location'] or '').casefold())
                if mapped is not None:answer=mapped;fact_key=mapped_key
                from .preparation_policy import human_control
                if human_control({'label':data.question,'type':'text'}):answer=None;fact_key=None
                status="PROPOSED" if answer else "NEEDS_USER_INFORMATION"
                if answer and data.character_limit and len(answer)>data.character_limit:answer=None;status="NEEDS_USER_INFORMATION"
                provenance={"profile_version":profile.get('version'),"fact_key":fact_key,"sources":profile.get("fact_provenance",{}).get(fact_key,[]) if isinstance(fact_key,str) else fact_key}
                conn.execute("INSERT INTO application_answers VALUES(?,?,?,?,?,?,?)",(uuid.uuid4().hex,qid,1,answer,status,_json(provenance),stamp))
        return qid

    def answer_question(self,question_id,answer:str|None,provenance:str="USER"):
        with self.db.transaction() as conn:
            q=conn.execute("SELECT * FROM application_questions WHERE question_id=?",(question_id,)).fetchone()
            if not q:raise ValueError("question_not_found")
            value=(answer or "").strip();status="NEEDS_USER_INFORMATION" if not value else "USER_EDITED"
            if q["character_limit"] and len(value)>q["character_limit"]:raise ValueError("answer_exceeds_character_limit")
            version=conn.execute("SELECT COALESCE(MAX(version),0)+1 FROM application_answers WHERE question_id=?",(question_id,)).fetchone()[0]
            conn.execute("INSERT INTO application_answers VALUES(?,?,?,?,?,?,?)",(uuid.uuid4().hex,question_id,version,value or None,status,_json({"source":provenance}),now()))
        return {"question_id":question_id,"version":version,"status":status}

    def add_contact(self,job_key,data:ContactInput):
        if data.verification_status=="VERIFIED" and (not data.email or not (data.source_url or data.source_message_id)):raise ValueError("verified_contact_requires_email_and_source")
        if data.verification_status=="VERIFIED" and data.email and data.email.split("@",1)[0].casefold().replace("-","").replace("_","") in {"noreply","donotreply","notifications","notification"}:raise ValueError("verified_contact_must_be_role_related_person")
        if data.verification_status=="VERIFIED" and not any(term in data.role_relevance.casefold() for term in ("recruit","talent","hiring","human resources","hr","role contact")):raise ValueError("verified_contact_role_relevance_required")
        cid=uuid.uuid4().hex;stamp=now()
        with self.db.transaction() as conn:
            if not conn.execute("SELECT 1 FROM job_operational_state WHERE job_key=?",(job_key,)).fetchone():raise ValueError("job_not_found")
            conn.execute("INSERT INTO contact_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(cid,job_key,data.name,data.employer,data.email,data.source_url,data.source_message_id,data.role_relevance,data.verification_status,stamp if data.verification_status=="VERIFIED" else None,stamp,stamp))
            packet=conn.execute("SELECT packet_id,missing_information FROM application_packets WHERE job_key=?",(job_key,)).fetchone()
            if packet and data.verification_status=="VERIFIED":conn.execute("UPDATE application_packets SET status=?,updated_at=? WHERE packet_id=?",(PacketStatus.REVIEW_DRAFT_READY.value,stamp,packet["packet_id"]))
        return cid

    def research_stored_contacts(self,limit=100):
        """Classify addresses explicitly present in stored official vacancy text; never guess."""
        from .m2d import M2DEngine
        with self.db.transaction() as conn:
            rows=conn.execute("""SELECT p.job_key,j.company,j.description,COALESCE(j.canonical_application_url,j.application_url) url
                FROM application_packets p JOIN jobs j ON j.id=p.job_id ORDER BY j.match_score DESC,p.job_key LIMIT ?""",(limit,)).fetchall()
        result={"considered":len(rows),"checked":0,"verified_new":0,"verified_existing":0,"none_found":0,"rejected":0}
        m2d=M2DEngine(self.db)
        for row in rows:
            description=row["description"] or "";addresses=sorted(set(re.findall(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",description)));accepted=[]
            for email in addresses:
                index=description.casefold().find(email.casefold());excerpt=" ".join(description[max(0,index-220):index+len(email)+220].split());local=email.split("@",1)[0].casefold().replace("-","").replace("_","")
                disallowed=local in {"noreply","donotreply","notifications","notification"} or any(term in local for term in ("accessibility","privacy","security","support")) or (local.startswith("hr") and any(term in excerpt.casefold() for term in ("reasonable accommodation","need an accommodation","accessibility request")))
                relevant=local.startswith(("careers","recruit","talent","hiring")) and any(term in excerpt.casefold() for term in ("application","interview","hiring","applicant"))
                if disallowed or not relevant:result["rejected"]+=1;continue
                accepted.append((email,excerpt))
            result["checked"]+=1
            if accepted:
                for email,excerpt in accepted:
                    with self.db.transaction() as conn:exists=conn.execute("SELECT 1 FROM contact_evidence WHERE job_key=? AND lower(email)=lower(?)",(row["job_key"],email)).fetchone()
                    if not exists:self.add_contact(row["job_key"],ContactInput(name=f"{row['company']} Careers Team",employer=row["company"],email=email,source_url=row["url"],role_relevance="Official vacancy hiring-process evidence: "+excerpt[:800],verification_status="VERIFIED"));result["verified_new"]+=1
                    else:result["verified_existing"]+=1
                m2d.record_evidence(row["job_key"],"recruiter_contact","PASS",factual=f"Stored official vacancy provides {len(accepted)} role-related hiring address(es).",evidence_url=row["url"])
            else:
                m2d.record_evidence(row["job_key"],"recruiter_contact","FAIL",factual="Stored vacancy text was checked; no qualifying role-related recruiter or hiring address was found.",evidence_url=row["url"]);result["none_found"]+=1
        from .automatic_drafts import process
        result['automatic_drafts']=process(self.db,engine=self)
        return result

    def create_draft(self,packet_id,request:DraftRequest,adapter):
        from .runtime_policy import require_external_write
        if request is None or not request.authorization_id:require_external_write('gmail_draft')
        if request.intent=="RECRUITER_REPLY" and not request.received_message_id:raise ValueError("reply_message_id_required")
        received=request.received_message_id or "";stamp=now()
        with self.db.transaction() as conn:
            packet=conn.execute("SELECT * FROM application_packets WHERE packet_id=?",(packet_id,)).fetchone();contact=conn.execute("SELECT * FROM contact_evidence WHERE contact_id=?",(request.contact_id,)).fetchone()
            if not packet or not contact or contact["job_key"]!=packet["job_key"]:raise ValueError("packet_or_contact_not_found")
            if contact["verification_status"]!="VERIFIED" or not contact["email"]:raise ValueError("verified_recipient_required")
            state=conn.execute("SELECT lifecycle,readiness FROM job_operational_state WHERE job_key=?",(packet["job_key"],)).fetchone()
            if state["lifecycle"]=="CLOSED" or state["readiness"]=="EXCLUDED":raise ValueError("incompatible_job")
            from .application_state import submission_projection
            submitted=submission_projection(conn,packet['job_id'])['application_outcome']!='NOT_SUBMITTED'
            if submitted and request.intent!="RECRUITER_REPLY":raise ValueError("previous_submission_blocks_repeat")
            version=conn.execute("SELECT * FROM application_packet_versions WHERE packet_id=? AND version=?",(packet_id,packet["current_version"])).fetchone()
            if request.authorization_id:
                from .runtime_policy import draft_payload
                payload_hash=draft_payload(to=contact['email'],subject=version['subject'],text=version['email_text'],html=version['email_html'],thread_message_id=request.received_message_id)
                require_external_write('gmail_draft',root=self.db.path.parent/'action-authorizations',
                    authorization_id=request.authorization_id,target=contact['email'],payload_hash=payload_hash,
                    snapshot_hash=self.draft_snapshot(packet_id,request,conn=conn))
            opid=uuid.uuid4().hex
            try:conn.execute("INSERT INTO gmail_draft_operations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(opid,packet["job_key"],request.contact_id,request.intent,received,packet_id,packet["current_version"],"PENDING",None,None,None,stamp,stamp))
            except sqlite3.IntegrityError:raise ValueError("duplicate_draft_operation") from None
            conn.execute("UPDATE application_packets SET status=?,updated_at=? WHERE packet_id=?",(PacketStatus.GMAIL_DRAFT_PENDING.value,stamp,packet_id))
            version=conn.execute("SELECT * FROM application_packet_versions WHERE packet_id=? AND version=?",(packet_id,packet["current_version"])).fetchone()
        try:
            kwargs=dict(to=contact["email"],subject=version["subject"],text=version["email_text"],html=version["email_html"],thread_message_id=request.received_message_id)
            if request.authorization_id:kwargs['authorization_id']=request.authorization_id
            result=adapter.create_draft(**kwargs)
            if not result.get("id"):raise RuntimeError("gmail_response_missing_draft_id")
        except Exception:
            with self.db.transaction() as conn:conn.execute("UPDATE gmail_draft_operations SET state='UNCERTAIN',error_code='gmail_outcome_unknown',updated_at=? WHERE operation_id=?",(now(),opid));conn.execute("UPDATE application_packets SET status=?,updated_at=? WHERE packet_id=?",(PacketStatus.GMAIL_DRAFT_UNCERTAIN.value,now(),packet_id))
            raise ValueError("gmail_draft_outcome_uncertain") from None
        with self.db.transaction() as conn:conn.execute("UPDATE gmail_draft_operations SET state='SAVED',gmail_draft_id=?,gmail_message_id=?,updated_at=? WHERE operation_id=?",(result["id"],(result.get("message") or {}).get("id"),now(),opid));conn.execute("UPDATE application_packets SET status=?,updated_at=? WHERE packet_id=?",(PacketStatus.GMAIL_DRAFT_SAVED.value,now(),packet_id))
        return {"operation_id":opid,"status":"GMAIL_DRAFT_SAVED","gmail_draft_id":result["id"],"manual_files_pending":True}

    def draft_snapshot(self,packet_id,request,conn=None):
        """Recheck packet/profile/vacancy/contact and actual required-document bytes."""
        if conn is None:
            with self.db.transaction() as opened:return self.draft_snapshot(packet_id,request,opened)
        from .document_manifest import sha256,resolve_approved_document
        packet=conn.execute('SELECT * FROM application_packets WHERE packet_id=?',(packet_id,)).fetchone()
        if not packet:raise ValueError('packet_not_found')
        job=conn.execute('SELECT * FROM jobs WHERE id=?',(packet['job_id'],)).fetchone()
        contact=conn.execute('SELECT * FROM contact_evidence WHERE contact_id=?',(request.contact_id,)).fetchone()
        version=conn.execute('SELECT * FROM application_packet_versions WHERE packet_id=? AND version=?',(packet_id,packet['current_version'])).fetchone()
        documents=self._documents();actual={}
        for name in json.loads(packet['required_documents']):
            item=documents.get(name,{})
            value=resolve_approved_document(item,self.db.path.parent)
            actual[name]=sha256(value)
            if actual[name]!=item.get('sha256'):raise ValueError('document_version_mismatch')
        profile_version,profile=self._profile(conn)
        return _hash(dict(packet=dict(packet),version=dict(version),job=dict(job),
                          contact=dict(contact) if contact else None,profile=profile,
                          profile_version=profile_version,documents=documents,actual=actual,
                          intent=request.intent,received_message_id=request.received_message_id))

    def resolve_uncertain(self,operation_id,outcome,gmail_draft_id=None):
        with self.db.transaction() as conn:
            op=conn.execute("SELECT * FROM gmail_draft_operations WHERE operation_id=?",(operation_id,)).fetchone()
            if not op or op["state"]!="UNCERTAIN":raise ValueError("uncertain_operation_not_found")
            if outcome=="SAVED" and not gmail_draft_id:raise ValueError("gmail_draft_id_required")
            state="SAVED" if outcome=="SAVED" else "RESOLVED_NO_DRAFT";status=PacketStatus.GMAIL_DRAFT_SAVED.value if state=="SAVED" else PacketStatus.REVIEW_DRAFT_READY.value
            conn.execute("UPDATE gmail_draft_operations SET state=?,gmail_draft_id=?,updated_at=? WHERE operation_id=?",(state,gmail_draft_id,now(),operation_id));conn.execute("UPDATE application_packets SET status=?,updated_at=? WHERE packet_id=?",(status,now(),op["packet_id"]))
        return {"operation_id":operation_id,"state":state}
