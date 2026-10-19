"""Local approved-document inventory. Manifest output belongs under ignored data/."""
from __future__ import annotations
import hashlib,json,re,zipfile
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
from .database import now
from .resume_review import extract

APPROVED_HOSTS={"linkedin.com","www.linkedin.com","github.com","www.github.com"}

def sha256(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda:handle.read(1024*1024),b""):digest.update(block)
    return digest.hexdigest()


def resolve_approved_document(item,private_root):
    """Resolve an approved version, including its original immutable local copy."""
    expected=item.get('sha256') or ''
    if not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('document_hash_missing')
    candidates=[Path(item[name]) for name in ('local_path','path') if item.get(name)]
    suffix=Path(item.get('canonical_name','')).suffix.lower()
    if suffix in {'.pdf','.docx','.png'}:
        candidates.append(Path(private_root)/'resumes'/(expected+suffix))
    for path in candidates:
        if path.is_file():
            if sha256(path)!=expected:raise ValueError('document_version_mismatch')
            return path
    raise ValueError('required_document_unavailable')

def document_links(path:Path)->list[str]:
    links=[]
    if path.suffix.casefold()==".pdf":
        from pypdf import PdfReader
        for page in PdfReader(path).pages:
            for annotation in page.get("/Annots") or []:
                item=annotation.get_object();action=item.get("/A")
                if action and action.get("/URI"):links.append(str(action["/URI"]))
    elif path.suffix.casefold()==".docx":
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.startswith("word/_rels/") and name.endswith(".rels"):
                    root=ET.fromstring(archive.read(name))
                    links.extend(item.attrib["Target"] for item in root if item.attrib.get("TargetMode")=="External" and item.attrib.get("Target"," ").startswith(("http://","https://")))
    return sorted(set(links))

def resume_safety(path:Path)->dict:
    text="\n".join(value for _,value in extract(path));links=document_links(path);unapproved=[]
    for link in links:
        parsed=urlsplit(link);host=(parsed.hostname or "").casefold()
        if parsed.scheme in {"http","https"} and host not in APPROVED_HOSTS:unapproved.append(link)
    return {"portfolio_text_present":bool(re.search(r"(?i)\bportfolio\b",text)),"unapproved_external_link_count":len(unapproved),"approved_link_hosts":sorted({urlsplit(link).hostname for link in links if (urlsplit(link).hostname or "").casefold() in APPROVED_HOSTS}),"extracted_sections":len(extract(path))}

def write_manifest(entries:list[dict],target:Path):
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps({"created_at":now(),"documents":entries},indent=2)+"\n",encoding="utf-8")
