"""GET-only Amazon public search interface observed in official search UI code.

This interface has no documented stability or rate SLA. Scope is country IND;
10,000 is the UI result cap, never evidence of complete employer coverage.
"""
import json
import re
from datetime import datetime

from .classification import extract_requirements
from .models import JobInput


class AmazonConnector:
    def fetch(self,source,reader,checkpoint):
        from .public_connectors import Batch,ProviderError
        scope={'country':'IND','query':'','sort':'recent'}
        offset=checkpoint.get('next_offset',0) if not checkpoint.get('complete') else 0
        if not isinstance(offset,int) or isinstance(offset,bool) or offset<0:raise ProviderError('invalid_checkpoint')
        if offset and checkpoint.get('scope')!=scope:raise ProviderError('checkpoint_scope_mismatch')
        rows=[];seen_pages=set();pages=0;start=offset;total=None
        membership=set(checkpoint.get('scan_seen_ids',[])) if offset else set()
        def batch(complete,reason,retry_after=0):
            return Batch(rows,{'scope':scope,'complete':complete,'start_offset':start,'next_offset':0 if complete else offset,
                'scan_seen_ids':sorted(membership),
                'end_offset':offset,'total_found':total,'result_cap':10000,'pages':pages,'termination_reason':reason,'retry_after':retry_after})
        while True:
            try:
                data,_,_=reader.get('https://www.amazon.jobs/en/search.json',{'normalized_country_code[]':'IND','offset':offset,'result_limit':reader.budget.settings.page_size,'sort':'recent'})
            except ProviderError as error:
                if not rows:raise
                return batch(False,error.code,error.retry_after)
            if not isinstance(data,dict) or data.get('error') or not isinstance(data.get('jobs'),list):
                if rows:return batch(False,'invalid_board_response')
                raise ProviderError('invalid_board_response')
            page=data['jobs'];total=data.get('hits')
            if not isinstance(total,int) or isinstance(total,bool) or total<0 or len(page)>reader.budget.settings.page_size:
                if rows:return batch(False,'invalid_pagination')
                raise ProviderError('invalid_pagination')
            if not page and offset<min(total,10000):
                if rows:return batch(False,'invalid_pagination')
                raise ProviderError('invalid_pagination')
            if len(rows)+len(page)>reader.budget.settings.max_records:return batch(False,'record_limit_exceeded')
            signature=tuple((str(record.get('id')),str(record.get('id_icims')),record.get('job_path')) for record in page if isinstance(record,dict))
            if page and signature in seen_pages:return batch(False,'repeated_page_or_id')
            seen_pages.add(signature)
            for index,record in enumerate(page):
                if not isinstance(record,dict):
                    record={'id':f'invalid-{offset+index}'};page[index]=record;continue
                path_id=re.match(r'/en/jobs/([A-Za-z0-9_-]+)/',record.get('job_path') or '')
                identifier=record.get('id_icims') or (path_id[1] if path_id else record.get('id'))
                # Public search includes non-ICIMS requisitions. Preserve their
                # actual identifiers; malformed rows are rejected individually.
                record['search_id']=record.get('id');record['id']=str(identifier or f'invalid-{offset+index}')
                membership.add(record['id'])
            reader.counters['records_fetched']+=len(page);rows.extend(page);offset+=len(page);pages+=1
            if offset>=10000:return batch(False,'search_index_result_cap')
            if offset>=total:return batch(True,'end_of_results')

    def normalize(self,source,record):
        from .public_connectors import plain_text
        path=record.get('job_path','')
        if not re.fullmatch(r'/en/jobs/'+re.escape(str(record['id']))+r'/[A-Za-z0-9_-]+',path):raise ValueError('invalid_vacancy_path')
        if record.get('country_code')!='IND':raise ValueError('out_of_scope_country')
        locations=[]
        for raw in record.get('locations') or []:
            item=json.loads(raw) if isinstance(raw,str) else raw
            if not isinstance(item,dict):raise ValueError('invalid_location')
            locations.append(item)
        description=plain_text('\n'.join([record.get('description') or '', 'Qualifications',record.get('basic_qualifications') or '', 'Preferred qualifications',record.get('preferred_qualifications') or '']))
        # Source dates have day precision. Do not invent hours from receipt/index time.
        published=None
        if record.get('posted_date'):
            try:published=datetime.strptime(record['posted_date'],'%B %d, %Y').date().isoformat()
            except (ValueError,TypeError):pass
        evidence=extract_requirements(description)|{'country':'IN','published_at':published,'timestamp_provenance':'amazon.posted_date',
            'publication_precision':'DAY','source_locations':locations,'employment_type':record.get('job_schedule_type'),'description_truncated':len(description)>20000}
        location='; '.join(dict.fromkeys(item.get('location') or item.get('city') or '' for item in locations)) or record.get('location') or 'India'
        url='https://www.amazon.jobs'+path
        job=JobInput(source=source.id,source_job_id=str(record['id']),company=record.get('company_name') or source.company,title=record['title'],location=location[:200],
            work_mode='remote' if locations and all(item.get('type')=='VIRTUAL' for item in locations) else 'unknown',description=description[:20000],skills=evidence['mentioned'],application_url=url)
        return job,url,evidence
