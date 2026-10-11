"""Explicit local resume extraction. Resume text is untrusted data, never instructions."""
import hashlib,re,uuid
from pathlib import Path
from pydantic import Field
from .models import StrictModel,clean,key

EXTRACTOR_VERSION="1"
SKILLS=("angular","react","javascript","typescript",".net","sql","python","fastapi","rag","faiss","embeddings","ollama","data science","machine learning")

class FactDecision(StrictModel):
    action:str=Field(pattern="^(ACCEPTED|REJECTED)$")
    reviewed_value:str|None=Field(default=None,max_length=200)

def extract(path:Path):
    if path.stat().st_size>5*1024*1024:raise ValueError("resume_too_large")
    if path.suffix.lower()==".pdf":
        from pypdf import PdfReader
        reader=PdfReader(path)
        if reader.is_encrypted:raise ValueError("encrypted_resume")
        if len(reader.pages)>30:raise ValueError("resume_page_limit")
        sections=[(f"page {i}",page.extract_text() or "") for i,page in enumerate(reader.pages,1)]
    elif path.suffix.lower()==".docx":
        from docx import Document
        paragraphs=Document(path).paragraphs
        if len(paragraphs)>1000:raise ValueError("resume_paragraph_limit")
        sections=[(f"paragraph {i}",p.text) for i,p in enumerate(paragraphs,1) if p.text.strip()]
    else:raise ValueError("unsupported_resume")
    if sum(len(text) for _,text in sections)>200000:raise ValueError("resume_text_limit")
    return sections

def propose(sections):
    facts=[];seen=set()
    for ref,text in sections:
        normalized=key(text)
        for skill in SKILLS:
            if re.search(r"(?<!\w)"+re.escape(skill)+r"(?!\w)",normalized) and skill not in seen:
                seen.add(skill);facts.append({"id":uuid.uuid4().hex,"category":"SKILL_UNVERIFIED","value":skill,"source_ref":ref,"confidence":"MEDIUM"})
        if re.search(r"\b(master|bachelor|degree|university)\b",normalized) and len(text)<500:
            value=clean(text)[:200]; marker=("EDUCATION",value)
            if marker not in seen:seen.add(marker);facts.append({"id":uuid.uuid4().hex,"category":"EDUCATION","value":value,"source_ref":ref,"confidence":"MEDIUM"})
    return facts[:100]
