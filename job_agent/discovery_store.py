"""Incremental source snapshots and transactional canonical job updates."""
import json
import sqlite3

from .classification import rank
from .database import now
from .models import JobInput, Status
from .service import content_signature, digest, identity, serialize_job
from .freshness import discovery_priority, location_bucket, normalize_skills, utc_timestamp


def _write_job(conn, job, job_id, match, listing, source_id, timestamp, existing=None):
    fields = job.model_dump(mode="json")
    fields.pop("source")
    fields.pop("source_job_id")
    fields["skills"] = json.dumps(fields["skills"])
    elig = match["eligibility"]
    published_at,published_confidence=utc_timestamp(match["evidence"].get("published_at"))
    source_updated_at,_=utc_timestamp(match["evidence"].get("source_updated_at"))
    if match["evidence"].get("experience"):
        fields["required_experience_min"]=match["evidence"]["experience"]["min"]
        fields["required_experience_max"]=match["evidence"]["experience"]["max"]
        fields["experience_scope"]=match["evidence"]["experience"].get("scope")
    fields.update(identity_key=identity(job), match_score=match["score"], match_detail=json.dumps(match), category=match["category"], priority=match["priority"], listing_url=listing, discovery_detail=json.dumps({"owner_source": source_id, "evidence": match["evidence"]}), last_seen=timestamp, last_changed=timestamp, updated_at=timestamp,
        eligibility_state=elig["state"], eligibility_explanation=elig["explanation"], eligibility_evidence=elig["evidence"], eligibility_confidence=elig["confidence"], eligibility_evaluated_at=elig["evaluated_at"], seniority_level=match["seniority_level"], activity_status="ACTIVE", last_verified=timestamp, missing_scans=0, duplicate_group=identity(job), canonical_application_url=listing or job.application_url, content_hash=content_signature(job.model_dump(mode="json")),
        published_at=published_at,source_updated_at=source_updated_at,timestamp_provenance=match["evidence"].get("timestamp_provenance"),timestamp_confidence=published_confidence,discovery_priority=discovery_priority(match["score"],elig["state"],published_at),location_bucket=location_bucket(job.location,elig["state"],job.work_mode),required_skills=json.dumps(normalize_skills(match["evidence"]["required"])),preferred_skills=json.dumps(normalize_skills(match["evidence"]["preferred"])))
    if match['evidence'].get('source_active') is False:
        fields['activity_status']='CLOSED'
    if existing:
        conn.execute("UPDATE jobs SET " + ",".join(name + "=?" for name in fields) + " WHERE id=?", list(fields.values()) + [job_id])
    else:
        fields.update(id=job_id, status=Status.NEW, created_at=timestamp, first_seen=timestamp)
        conn.execute("INSERT INTO jobs (" + ",".join(fields) + ") VALUES (" + ",".join("?" for _ in fields) + ")", list(fields.values()))
        conn.execute("INSERT INTO status_history(job_id, previous_status, status, created_at) VALUES (?, NULL, ?, ?)", (job_id, Status.NEW, timestamp))


def persist_batch(db, source, connector, records, background, profile, counters, budget):
    with db.transaction() as conn:
        conn.execute("BEGIN IMMEDIATE")
        timestamp = now()
        seen = set()
        for record in records:
            budget.check()
            previous_counts = counters.copy()
            conn.execute("SAVEPOINT listing")
            try:
                source_id = record.get("id") if isinstance(record, dict) else None
                if not isinstance(source_id, (str, int)) or isinstance(source_id, bool) or not str(source_id) or len(str(source_id)) > 200:
                    raise ValueError("invalid_source_id")
                source_key = str(source_id)
                if source_key in seen:
                    counters["duplicates"]+=1;conn.execute("RELEASE listing");continue
                seen.add(source_key)
                raw_hash = digest(record)
                reference = conn.execute("SELECT * FROM source_references WHERE source=? AND source_key=?", (source.id, source_key)).fetchone()
                if reference and reference["raw_hash"] == raw_hash:
                    conn.execute("UPDATE source_references SET last_seen=? WHERE id=?", (timestamp, reference["id"]))
                    conn.execute("UPDATE jobs SET last_seen=? WHERE id=?", (timestamp, reference["job_id"]))
                    conn.execute("UPDATE jobs SET activity_status=?, last_verified=?, missing_scans=0 WHERE id=? AND json_extract(discovery_detail,'$.owner_source')=?", ('CLOSED' if record.get('active') is False else 'ACTIVE',timestamp, reference["job_id"],source.id))
                    counters["unchanged_jobs"] += 1
                    conn.execute("RELEASE listing")
                    continue
                job, listing, evidence = connector.normalize(source, record)
                if job.source_job_id != source_key:
                    raise ValueError("source_id_mismatch")
                hash_value = content_signature(job.model_dump(mode="json"))
                ident = identity(job)
                if reference:
                    existing = conn.execute("SELECT * FROM jobs WHERE id=?", (reference["job_id"],)).fetchone()
                else:
                    matches = conn.execute("""SELECT DISTINCT j.* FROM jobs j LEFT JOIN source_references r ON j.id=r.job_id
                        WHERE j.application_url=? OR j.listing_url=? OR r.listing_url=?""", (job.application_url, listing, listing)).fetchall()
                    if len(matches) > 1:
                        raise ValueError("identity_conflict")
                    existing = matches[0] if matches else None
                if existing and existing["is_sample"]:
                    raise ValueError("sample_identity_conflict")
                if existing and not reference:
                    counters["duplicates"] += 1
                job_id = existing["id"] if existing else digest([source.id, source_key])
                prior_detail = json.loads(existing["discovery_detail"]) if existing and existing["discovery_detail"] else None
                semantic=lambda value:{k:v for k,v in value.items() if k not in {"published_at","source_updated_at","timestamp_provenance"}}
                cross_source_alias=bool(existing and prior_detail and prior_detail["owner_source"]!=source.id)
                changed = existing is None or prior_detail is None or bool(reference) and not cross_source_alias and (content_signature(serialize_job(existing)) != hash_value or existing["listing_url"] != listing or existing["application_url"] != job.application_url or semantic(prior_detail["evidence"]) != semantic(evidence))
                if changed:
                    if existing and existing["discovery_detail"] and json.loads(existing["discovery_detail"])["owner_source"] != source.id:
                        raise ValueError("cross_source_content_conflict")
                    match = rank(job, evidence, background, profile)
                    _write_job(conn, job, job_id, match, listing, source.id, timestamp, existing)
                    counters["updated_jobs" if existing else "new_jobs"] += 1
                    db.audit(conn, "LIVE_JOB_UPDATED" if existing else "LIVE_JOB_DISCOVERED", {"source_id": source.id}, job_id)
                elif reference:
                    counters["unchanged_jobs"] += 1
                    conn.execute("UPDATE jobs SET last_seen=? WHERE id=?", (timestamp, job_id))
                    if not cross_source_alias:
                        conn.execute("UPDATE jobs SET activity_status=?, last_verified=?, missing_scans=0 WHERE id=?", ('CLOSED' if evidence.get('source_active') is False else 'ACTIVE',timestamp, job_id))
                snapshot = json.dumps({"job": job.model_dump(mode="json"), "listing_url": listing, "evidence": evidence})
                if reference:
                    conn.execute("""UPDATE source_references SET content_hash=?, raw_hash=?, snapshot=?, listing_url=?, application_url=?, last_seen=?, last_changed=? WHERE id=?""", (hash_value, raw_hash, snapshot, listing, job.application_url, timestamp, timestamp if changed else reference["last_changed"], reference["id"]))
                else:
                    conn.execute("""INSERT INTO source_references(job_id, source, source_key, source_job_id, application_url, content_hash, imported_at, first_seen, last_seen, last_changed, raw_hash, listing_url, snapshot) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (job_id, source.id, source_key, source_key, job.application_url, hash_value, timestamp, timestamp, timestamp, timestamp, raw_hash, listing, snapshot))
                conn.execute("RELEASE listing")
            except (ValueError, KeyError, TypeError, AttributeError, sqlite3.IntegrityError) as failure:
                conn.execute("ROLLBACK TO listing")
                conn.execute("RELEASE listing")
                counters.update(previous_counts)
                counters["rejected_records"] += 1
                safe_codes={"invalid_source_id","source_id_mismatch","identity_conflict","sample_identity_conflict","cross_source_content_conflict","ambiguous_same_source_identity","invalid_source_record","invalid_source_url","invalid_location","invalid_description"}
                code=str(failure) if isinstance(failure,ValueError) and str(failure) in safe_codes else "invalid_or_conflicting_record"
                db.audit(conn, "LIVE_RECORD_REJECTED", {"source_id": source.id, "code": code})


def touch_not_modified(db, source_id, counters):
    with db.transaction() as conn:
        timestamp = now()
        count = conn.execute("SELECT COUNT(*) FROM source_references WHERE source=?", (source_id,)).fetchone()[0]
        conn.execute("UPDATE source_references SET last_seen=? WHERE source=?", (timestamp, source_id))
        conn.execute("UPDATE jobs SET last_seen=?, last_verified=?, activity_status=CASE WHEN json_extract(discovery_detail,'$.evidence.source_active')=0 THEN 'CLOSED' ELSE 'ACTIVE' END, missing_scans=0 WHERE id IN (SELECT job_id FROM source_references WHERE source=?) AND json_extract(discovery_detail,'$.owner_source')=?", (timestamp, timestamp, source_id,source_id))
        counters["unchanged_jobs"] += count


def reconcile_missing(db, source_id, seen_keys):
    """Advance lifecycle only after successful complete scans; two misses are cautious."""
    with db.transaction() as conn:
        rows=conn.execute("SELECT job_id,source_key FROM source_references WHERE source=?",(source_id,)).fetchall()
        for row in rows:
            if row["source_key"] in seen_keys: continue
            conn.execute("UPDATE jobs SET missing_scans=missing_scans+1, activity_status=CASE WHEN missing_scans+1>=2 THEN 'CLOSED' ELSE 'POSSIBLY_CLOSED' END WHERE id=? AND json_extract(discovery_detail,'$.owner_source')=?",(row["job_id"],source_id))
