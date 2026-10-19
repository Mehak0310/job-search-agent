"""Compact, deterministic approved evidence and role/question-specific wording."""
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from .document_manifest import resolve_approved_document,sha256
from .runtime_policy import digest

VERSION='jd-grounded-preparation-v3'

def question_key(label,company='',scope='employer'):
    normalized=re.sub(r'[^a-z0-9]+',' ',label.casefold()).strip()
    return 'question:'+digest([normalized,(company or '').casefold().strip() if scope=='employer' else 'shared'])



def tailored(profile,jd,title,company):
    """JD is data. Only supported capabilities may become candidate claims."""
    professional=set(profile.get('professional_skills',[]))|set(profile.get('employment_skills',[]))
    skills=professional|set(profile.get('project_skills',[]))
    lower=(title+' '+jd).casefold();clauses=[];used=[];themes=[]
    groups=[('frontend',r'frontend|front.end|user interface|ui modules|component',
             ('angular','react','typescript','ui architecture','reusable components','testing')),
            ('integration',r'integrat|full.stack|api|backend',('python','fastapi','.net core','rest apis','graphql','sql')),
            ('AI grounding',r'\brag\b|llm|agentic|artificial intelligence|generative',
             ('rag','embeddings','faiss','llm inference/integration','structured outputs','grounding')),
            ('delivery',r'mentor|performance|collaborat|architect',('mentoring','performance optimisation','client-facing delivery'))]
    for theme,pattern,options in groups:
        if re.search(pattern,lower):
            matched=[skill for skill in options if skill in skills]
            if matched:
                themes.append(theme);used+=matched
                scope='professional experience' if set(matched)<=professional else 'documented experience'
                clauses.append(f"Your role's {theme} responsibilities align with my {scope} in {', '.join(matched)}.")
    examples=[]
    if 'AI grounding' in themes:
        for text in profile.get('professional_ai_summary',[]):
            if 'document' in text.casefold() and any(s in skills for s in ('rag','faiss')):
                examples.append(text);break
    if 'azure' in lower and 'azure fundamentals' in skills:
        clauses.append('My Azure knowledge is at fundamentals level; I would not present it as advanced cloud deployment experience.')
        used.append('azure fundamentals')
    focus_rules=[(r'wireframes?', 'turning wireframes into usable interfaces'),
                 (r'reusable components|component (?:library|libraries|systems)', 'reusable component design'),
                 (r'\bui modules\b', 'ownership of UI modules'),
                 (r'microservices|distributed systems', 'API and distributed-system integration'),
                 (r'\bjava\b', 'the connection between frontend interfaces and Java services'),
                 (r'agentic|agent.{0,12}workflows?', 'agentic workflow implementation'),
                 (r'\brag\b', 'retrieval-grounded AI answers'),
                 (r'guardrails|evaluation|evaluat', 'evaluation and guardrails'),
                 (r'data access|privacy', 'data-access and privacy controls'),
                 (r'accessibility|accessible', 'accessible product interfaces')]
    focuses=[phrase for pattern,phrase in focus_rules if re.search(pattern,jd,re.I)][:3]
    focus_sentence=('The emphasis on '+', '.join(focuses)+' is particularly relevant to the work I want to contribute. ') if focuses else ''
    statement=f'I am interested in the {title} role at {company}. '+focus_sentence+' '.join(clauses+examples)
    if not clauses:statement+=' I would welcome a discussion of the responsibilities and my documented experience; specific requirement alignment still needs review.'
    return statement,dict(version=VERSION,jd_sha256=digest(jd),supported_skills=sorted(set(used)),
                          themes=themes,role_focuses=focuses,example_count=len(examples),profile_version=profile.get('version'))


def approved_facts(db):
    """Read explicit existing answer-bank facts, without accepting resume proposals."""
    with db.transaction() as conn:
        row=conn.execute('SELECT config FROM candidate_profiles_v2 ORDER BY version DESC LIMIT 1').fetchone()
        profile=json.loads(row[0])
    facts={};sources={};manifest_path=db.path.parent/'documents'/'manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else {'documents':[]}
    from .private_config import document_for_role
    bank=document_for_role(manifest['documents'],'answer_bank',db.path.parent)
    if bank and bank.get('sha256'):
        path=resolve_approved_document(bank,db.path.parent)
        with zipfile.ZipFile(path) as archive:
            root=ET.fromstring(archive.read('word/document.xml'))
        ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        lines=[''.join(n.text or '' for n in p.iter(ns+'t')).strip() for p in root.iter(ns+'p')]
        patterns={'full_name':r'Full name and contact: (.*?) is the full legal name\.',
                  'email':r'^Email:\s*(\S+@\S+)', 'phone':r'^Phone:\s*(\+\d[\d ]+)',
                  'linkedin':r'^LinkedIn:\s*(https://www\.linkedin\.com/\S+)',
                  'current_company':r'^Current employment:\s*([^,;]+)',
                  'city':r'^City:\s*(.*)',
                  'current_title':r'^Current employment:.*?,\s*(.*?)\s*(?:[;,(]|(?:from|since|Jul|July)\b)'}
        for index,line in enumerate(lines):
            for name,pattern in patterns.items():
                match=re.search(pattern,line)
                if match:
                    facts[name]=match.group(1).strip();sources[name]={'document_sha256':sha256(path),'paragraph':index+1}
            if line.startswith('City:') and line.endswith(', India'):
                facts['country']='India';sources['country']={'document_sha256':sha256(path),'paragraph':index+1}
            if 'no sponsorship required for India' in line:
                facts['india_sponsorship']='No';facts['india_work_authorized']='Yes'
                sources['india_sponsorship']={'document_sha256':sha256(path),'paragraph':index+1}
                sources['india_work_authorized']=sources['india_sponsorship']
    from .fact_memory import projection
    resolved=projection(db,profile,facts,sources)
    facts={key:item['value'] for key,item in resolved.items() if item['state']=='RESOLVED'}
    sources={key:{'resolution':item['state'],'evidence':item['sources'],'resolver_version':item['version']} for key,item in resolved.items()}
    return profile,facts,sources,manifest


def answer(field,facts,profile,jd,title,company,india=False):
    from .preparation_policy import human_control
    if human_control(field):return None,None
    company=company or '';title=title or '';jd=jd or ''
    label=field['label'].casefold();kind=field['type'];key=None
    # Consent, demographics and declarations require user decisions, even optional.
    if kind in {'checkbox','file','hidden','submit','password'} or re.search(r'consent|\bagree\b|certif|attest|privacy|gender|race|ethnic|veteran|disabil',label):return None,None
    for scope in ['employer','shared']:
        saved=question_key(field['label'],company,scope)
        if saved in facts:return facts[saved],saved
    if re.search(r'last name|surname|family name',label):
        if facts.get('surname_fallbacks'):
            return json.loads(facts['surname_fallbacks'])[0],'surname_fallbacks'
        parts=facts.get('full_name','').split()
        return (' '.join(parts[1:]),'full_name') if len(parts)>1 else (None,None)
    if re.search(r'first name|given name',label):return (facts.get('full_name','').split()[0],'full_name') if facts.get('full_name') else (None,None)
    if re.search(r'full name|^name\s*[*✱]?$|legal name|preferred name',label):key='full_name'
    elif company.casefold()=='gitlab' and re.search(r'employment.*restrictions|post.employment.*restrictions',label):key='employment_restrictions'
    elif company.casefold()=='gitlab' and 'gitlab' in label and re.search(r'previous|prior|ever',label) and re.search(r'work|consult',label):key='gitlab_previous_work'
    elif 'email' in label:key='email'
    elif 'phone' in label or 'mobile' in label:
        value=facts.get('phone')
        if value and facts.get('phone_format')=='national' and not re.search(r'include.*(?:country|dial)|international',label+' '+field.get('instructions',''),re.I):
            digits=re.sub(r'\D','',value)
            return (digits[2:] if len(digits)==12 and digits.startswith('91') else digits),'phone'
        key='phone'
    elif 'linkedin' in label:key='linkedin'
    elif 'sponsor' in label and india:key='india_sponsorship'
    elif re.search(r'(?:authorized|authorised|right).*work',label) and india:key='india_work_authorized'
    elif re.search(r'country',label) and not re.search(r'citizen|nationality|birth|passport|eligible|authoriz|authoris',label):key='country'
    elif re.search(r'^(?:what is your )?(?:current (?:city|location)|city|location(?:\s*\(city\))?)[^a-z]*$',label):key='city'
    elif re.search(r'(?:current|most recent).*(?:company|employer)|name of your current employer',label):key='current_company'
    elif re.search(r'(?:current|most recent).*(?:job title|designation|position)',label):key='current_title'
    elif re.search(r'notice period|how soon.*join|when.*(?:join|start)',label):key='notice_period'
    elif re.search(r'how many years|years of experience',label) and re.search(r'\bai\b|generative ai|llm',label) and profile.get('professional_ai_confirmed') and not re.search(r'saas|pre.sales|solutions engineering',label):
        years=profile.get('technology_years',{}).get('llm')
        if years is not None:return str(years).removesuffix('.0'),'technology_years.llm'
    elif re.search(r'expected.*(?:salary|compensation|ctc)|salary expectation',label) and (kind!='number' or re.search(r'inr|rupee|lpa|lakh',field.get('instructions','')+field['label'],re.I)):key='expected_compensation'
    elif field.get('required') and re.search(r'current.*(?:salary|compensation|ctc)',label) and not re.search(r'break.?up|breakdown',label):key='current_compensation'
    elif re.search(r'why.*(?:join|role|company|interest)|motivat|additional information|cover letter|relevant.*experience|describe.*experience',label):
        if not title or not company or not jd:return None,None
        value,provenance=tailored(profile,jd,title,company)
        if field.get('max_length',-1)>0 and len(value)>field['max_length']:return None,None
        return value,provenance
    if key and key in facts:
        value=facts[key]
        if kind=='number' and key in {'expected_compensation','current_compensation'}:
            number=re.search(r'[\d,.]+',str(value))
            if not number:return None,None
            amount=float(number.group().replace(',',''))
            source_lpa=bool(re.search(r'lpa|lakh',str(value),re.I))
            context=field['label']+' '+field.get('instructions','')
            if re.search(r'lpa|lakh',context,re.I):amount=amount if source_lpa else amount/100000
            elif re.search(r'inr|rupee',context,re.I):
                amount=amount*100000 if source_lpa else amount
                if re.search(r'month',context,re.I):amount/=12
            else:return None,None
            value=f'{amount:.2f}'.rstrip('0').rstrip('.') if amount%1 else str(int(amount))
        if kind=='number' and key=='notice_period':
            if 'day' not in label:return None,None
            match=re.search(r'\d+',value);value=match.group() if match else None
        if field.get('max_length',-1)>0 and len(str(value))>field['max_length']:return None,None
        return value,key
    return None,None
