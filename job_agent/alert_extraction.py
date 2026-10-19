"""Provider-specific local alert decoding. No network actions during parsing."""
import html
import re
from urllib.parse import parse_qsl,unquote,urlsplit,urlunsplit,urlencode
from pydantic import Field
from .models import StrictModel,clean
from .alert_links import alert_links

PARSER_VERSION='exact-vacancy-v3'
ROLE=re.compile(r'\b(engineer|developer|consultant|architect|analyst|manager|lead|specialist|designer|scientist)\b',re.I)
ACTION=re.compile(r'(?i)^(apply(?: now)?|unsubscribe.*|sign in|log.?in|view all jobs|more jobs.*|edit|manage.*|see new roles|find jobs|verify.*)$')


class AlertVacancy(StrictModel):
    url:str|None=None
    original_url:str=Field(max_length=12000)
    title:str|None=Field(default=None,max_length=200)
    company:str|None=Field(default=None,max_length=200)
    location:str|None=Field(default=None,max_length=200)
    blocker:str|None=None


def local_destination(value):
    value=html.unescape(html.unescape(value))
    for _ in range(4):
        try:
            p=urlsplit(value);host=(p.hostname or '').lower();q=dict(parse_qsl(p.query,max_num_fields=100))
            if p.scheme!='https' or p.username or p.password or p.port not in {None,443}:return None
        except ValueError:return None
        nested=None
        if host=='postoffice.hirist.tech' and p.path.startswith(('/CL0/','/CL1/')):
            nested=unquote(p.path.split('/')[2])
        elif host=='tr.naukri.com':nested=q.get('redirect')
        elif host in {'foundit.in','www.foundit.in'}:nested=q.get('return_url')
        elif host in {'www.google.com','google.com','www.linkedin.com','linkedin.com'}:nested=q.get('url')
        if not nested:return value
        value=nested
    return None


def exact_vacancy_url(value):
    from .m2d import GmailExportAdapter
    value=local_destination(value)
    if not value:return None
    p=urlsplit(value);host=(p.hostname or '').lower().removeprefix('www.');q=dict(parse_qsl(p.query));path=p.path.rstrip('/')
    if host=='naukri.com' and re.fullmatch(r'/jd/job-listings-[^/]+-\d{8,}',path):return urlunsplit(('https',p.netloc,path,'',''))
    if host in {'glassdoor.com','glassdoor.co.in'} and path=='/partner/jobListing.htm' and re.fullmatch(r'\d{6,}',q.get('jobListingId','')):
        return urlunsplit(('https',p.netloc,path,urlencode({'jobListingId':q['jobListingId']}),''))
    return GmailExportAdapter._specific_url(value)


def extract_alert(message,resolver=None):
    vacancies=[];unresolved=[];seen=set();duplicates=0
    if re.search(r'(?i)\b(webinar|course|profile views?|career advice)\b',message.subject):return {'vacancies':[],'unresolved':[],'duplicates':0,'classification':'MARKETING'}
    for link in alert_links(message.body,message.subject):
        parts=[clean(x) for x in link.get('text_parts',[]) if clean(x)];title=clean(link['title'])
        if ACTION.fullmatch(title):continue
        named=next((x for x in parts if ROLE.search(x) and not ACTION.fullmatch(x)),title if ROLE.search(title) and not title.startswith('https://') else None)
        company=None;location=None
        if named and parts and named in parts:
            index=parts.index(named)
            if index and not ROLE.search(parts[0]) and not re.search(r'\d|\u2605',parts[0]):company=parts[0][:200]
            for item in parts[index+1:]:
                if re.fullmatch(r'(?i)(noida|greater noida|gurgaon|gurugram|delhi|new delhi|mohali|chandigarh|remote|hyderabad|bangalore|bengaluru|pune)(?:[ ,].*)?',item):location=item[:200];break
        if named and not company and ' - ' in named:
            prefix,rest=named.split(' - ',1)
            if not ROLE.search(prefix) and ROLE.search(rest):company=prefix[:200];named=rest
        destination=local_destination(link['url']);url=exact_vacancy_url(link['url'])
        if not url and named and resolver:
            url=resolver(link['url'])
            if url:url=exact_vacancy_url(url)
        if url:
            if url in seen:duplicates+=1;continue
            seen.add(url);vacancies.append(AlertVacancy(url=url,original_url=link['url'],title=named[:200] if named else None,company=company,location=location))
        elif named and destination:
            p=urlsplit(destination)
            if (p.hostname=='engage.indeed.com' and p.path.startswith('/f/a/')) or (p.hostname in {'www.naukri.com','naukri.com'} and p.path.startswith('/durl/')):
                if link['url'] in seen:duplicates+=1;continue
                seen.add(link['url']);unresolved.append(AlertVacancy(original_url=link['url'],title=named[:200],company=company,location=location,blocker=getattr(resolver,'last_error',None) or 'opaque_tracking_destination_needs_permitted_resolution'))
    return {'vacancies':vacancies,'unresolved':unresolved,'duplicates':duplicates,'classification':'VACANCY' if vacancies else 'UNRESOLVED_ALERT' if unresolved else 'NO_SPECIFIC_VACANCY'}
