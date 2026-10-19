"""Documented public Posting API; metadata first, bounded resumable India scope.

https://developers.smartrecruiters.com/docs/endpoints
No customer API, authentication, applications or external writes.
"""
import re
from urllib.parse import urlsplit

from .classification import extract_requirements
from .models import JobInput


class SmartRecruitersConnector:
    def enrich(self, source, batch, reader, cached, preferences):
        """Verify relevant location/title metadata, reusing unchanged official JDs."""
        from .public_connectors import ProviderError
        from .classification import classify
        from .freshness import utc_timestamp
        from datetime import datetime, timedelta, timezone
        pending=[];cache_hits=0;verified=0
        for row in batch.records:
            old=cached.get(str(row['id']))
            verified_at=(old or {}).get('evidence',{}).get('detail_verified_at')
            try:cache_fresh=verified_at and datetime.fromisoformat(verified_at)>datetime.now(timezone.utc)-timedelta(hours=24)
            except (ValueError,TypeError):cache_fresh=False
            if old and cache_fresh and old['evidence'].get('detail_released_date')==row.get('releasedDate') and not old['evidence'].get('description_pending',True):
                if old['evidence'].get('source_active') is False:row['active']=False
                row['_detail_snapshot']=old;cache_hits+=1;continue
            location=row.get('location') or {};text=' '.join(str(location.get(k) or '') for k in ('city','region','fullLocation')).casefold()
            in_scope=location.get('remote') is True or 'remote' in text or any(value.casefold() in text for value in preferences.locations if value.casefold() not in {'remote india','delhi ncr'}) or 'delhi' in text or 'gurgaon' in text
            category,_=classify(row.get('name',''))
            published,_=utc_timestamp(row.get('releasedDate'))
            fresh=published is None or datetime.fromisoformat(published)>=datetime.now(timezone.utc)-timedelta(days=7)
            if not in_scope or category not in {'FRONTEND','FRONTEND_LEADERSHIP','AI_GENAI','FULLSTACK_AI','CONSULTING'} or not fresh:continue
            try:
                detail,_,_=reader.get(f"https://api.smartrecruiters.com/v1/companies/{source.board}/postings/{row['id']}",{})
                if not isinstance(detail,dict) or str(detail.get('id'))!=str(row['id']) or not isinstance(detail.get('jobAd'),dict):
                    raise ProviderError('invalid_detail_response')
                if str((detail.get('company') or {}).get('identifier',source.board)).casefold()!=source.board.casefold():
                    raise ProviderError('detail_employer_mismatch')
                # Keep list publication provenance; detail enrichment cannot substitute dates.
                row.update({k:detail[k] for k in ('jobAd','applyUrl','active') if k in detail});verified+=1
                row['_detail_verified_at']=datetime.now(timezone.utc).isoformat()
            except ProviderError as error:
                pending.append({'id':str(row['id']),'reason':error.code})
                batch.checkpoint['retry_after']=max(batch.checkpoint.get('retry_after',0),error.retry_after)
        batch.checkpoint.update(detail_verified=verified,detail_cache_hits=cache_hits,pending_details=pending)
        return batch

    def fetch(self, source, reader, checkpoint):
        from .public_connectors import Batch, ProviderError
        offset = checkpoint.get("next_offset", 0) if not checkpoint.get("complete") else 0
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ProviderError("invalid_checkpoint")
        start, rows, seen, pages = offset, [], set(), 0
        membership=set(checkpoint.get('scan_seen_ids',[])) if offset else set()
        scope = {"country": "in", "query": "", "board": source.board}
        if offset and checkpoint.get("scope") != scope:
            raise ProviderError("checkpoint_scope_mismatch")
        total = None
        while True:
            try:
                data, _, _ = reader.get(
                    f"https://api.smartrecruiters.com/v1/companies/{source.board}/postings",
                    {"country": "in", "limit": reader.budget.settings.page_size, "offset": offset},
                )
            except ProviderError as error:
                # Already retrieved pages are committed by the existing coordinator.
                # Retry starts at the first unread offset; no network inside writes.
                if not rows:
                    raise
                return Batch(rows, {"complete": False, "scope": scope, "start_offset": start,
                    "scan_seen_ids":sorted(membership),
                    "next_offset": offset, "pages": pages, "total_found": total,
                    "termination_reason": error.code, "retry_after": error.retry_after})
            if not isinstance(data, dict) or not isinstance(data.get("content"), list):
                raise ProviderError("invalid_board_response")
            page, total = data["content"], data.get("totalFound")
            if not isinstance(total, int) or isinstance(total, bool) or total < 0 or data.get("offset") != offset:
                raise ProviderError("invalid_pagination")
            if len(page) > reader.budget.settings.page_size or (not page and offset < total):
                raise ProviderError("invalid_pagination")
            if len(rows) + len(page) > reader.budget.settings.max_records:
                return Batch(rows, {"complete": False, "scope": scope, "start_offset": start,
                    "scan_seen_ids":sorted(membership),
                    "next_offset": offset, "pages": pages, "total_found": total,
                    "termination_reason": "record_limit_exceeded"})
            for record in page:
                if not isinstance(record, dict) or not re.fullmatch(r"[0-9]+", str(record.get("id", ""))):
                    raise ProviderError("invalid_source_record")
                if record["id"] in seen:
                    raise ProviderError("repeated_page_or_id")
                seen.add(record["id"])
                membership.add(str(record['id']))
            reader.counters["records_fetched"] += len(page)
            rows.extend(page); pages += 1; offset += len(page)
            if offset >= total:
                return Batch(rows, {"complete": True, "scope": scope, "start_offset": start,
                    "scan_seen_ids":sorted(membership),
                    "next_offset": 0, "end_offset": offset, "pages": pages,
                    "total_found": total, "termination_reason": "end_of_results"})

    def normalize(self, source, record):
        from .public_connectors import plain_text
        location = record.get("location") or {}
        company = record.get("company") or {}
        if str(company.get("identifier", "")).casefold() != source.board.casefold():
            raise ValueError("employer_identity_mismatch")
        if str(location.get("country", "")).casefold() != "in":
            raise ValueError("out_of_scope_country")
        sections = (record.get("jobAd") or {}).get("sections") or {}
        description = plain_text("\n".join(s.get("title", "")+"\n"+s.get("text", "") for s in sections.values() if isinstance(s, dict)))
        cached=record.get('_detail_snapshot')
        if cached:description=cached['job']['description']
        listing = f"https://jobs.smartrecruiters.com/{source.board}/{record['id']}"
        application = record.get("applyUrl") or listing
        parsed = urlsplit(application)
        if parsed.scheme != "https" or parsed.hostname not in {"jobs.smartrecruiters.com", "www.smartrecruiters.com"} or parsed.username or parsed.password or parsed.port not in {None, 443}:
            raise ValueError("unsafe_application_url")
        if not re.fullmatch('/'+re.escape(source.board)+'/'+re.escape(str(record['id']))+r'(?:-[^/]*)?/?',parsed.path,re.I):
            raise ValueError('generic_application_url')
        evidence = extract_requirements(description) | {
            "country": "IN", "published_at": record.get("releasedDate"),
            "timestamp_provenance": "smartrecruiters.releasedDate",
            "employment_type": record.get("typeOfEmployment"),
            "requisition_reference": record.get("refNumber"),
            "description_pending": not bool(description),
            "source_active": record.get('active') is not False,
            "detail_released_date": record.get('releasedDate') if description else None,
            "detail_verified_at": cached['evidence'].get('detail_verified_at') if cached else record.get('_detail_verified_at'),
            "official_detail_url": f"https://api.smartrecruiters.com/v1/companies/{source.board}/postings/{record['id']}",
        }
        job = JobInput(source=source.id, source_job_id=str(record["id"]), company=company.get("name") or source.company,
            title=record["name"], location=location.get("fullLocation") or ", ".join(filter(None, [location.get("city"), location.get("region"), "India"])),
            work_mode="remote" if location.get("remote") is True else "hybrid" if location.get("hybrid") is True else "unknown",
            description=description, skills=evidence["mentioned"], application_url=application)
        return job, listing, evidence
