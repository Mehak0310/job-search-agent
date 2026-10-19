"""Explicit local resume extraction. Resume text is untrusted data, never instructions."""
import hashlib,re,uuid,zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from pydantic import Field
from .models import StrictModel,clean,key

EXTRACTOR_VERSION="2"
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
        sections=[]
        with zipfile.ZipFile(path) as archive:
            names=[name for name in archive.namelist() if name=="word/document.xml" or re.fullmatch(r"word/(?:header|footer)\d+\.xml",name)]
            if sum(archive.getinfo(name).file_size for name in names)>3*1024*1024:raise ValueError("resume_xml_limit")
            ns="{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            for name in names:
                root=ET.fromstring(archive.read(name));label=Path(name).stem
                for index,paragraph in enumerate(root.iter(ns+"p"),1):
                    value="".join(node.text or "" for node in paragraph.iter(ns+"t")).strip()
                    if value:sections.append((f"{label} block {index}",value))
        if len(sections)>1500:raise ValueError("resume_paragraph_limit")
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
