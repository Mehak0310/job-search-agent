"""Validated M3 inputs. Employer and mailbox text remains untrusted data."""
from enum import StrEnum
from pydantic import Field,field_validator
from .models import StrictModel,clean

class PacketStatus(StrEnum):
    TEXT_PREPARED="TEXT_PREPARED"
    NEEDS_USER_INFORMATION="NEEDS_USER_INFORMATION"
    CONTACT_VERIFICATION_PENDING="CONTACT_VERIFICATION_PENDING"
    REVIEW_DRAFT_READY="REVIEW_DRAFT_READY"
    GMAIL_DRAFT_PENDING="GMAIL_DRAFT_PENDING"
    GMAIL_DRAFT_SAVED="GMAIL_DRAFT_SAVED"
    GMAIL_DRAFT_UNCERTAIN="GMAIL_DRAFT_UNCERTAIN"
    BLOCKED_INCOMPATIBLE="BLOCKED_INCOMPATIBLE"

class PacketEdit(StrictModel):
    subject:str=Field(min_length=1,max_length=300)
    email_text:str=Field(min_length=1,max_length=20000)
    email_html:str=Field(min_length=1,max_length=30000)
    supporting_statement:str=Field(min_length=1,max_length=10000)

class EmployerQuestion(StrictModel):
    question:str=Field(min_length=1,max_length=2000)
    source:str=Field(min_length=1,max_length=100)
    source_ref:str=Field(min_length=1,max_length=2000)
    character_limit:int|None=Field(default=None,ge=1,le=50000)
    field_kind:str=Field(default="TEXT",pattern="^(TEXT|SALARY|NOTICE|WORK_AUTHORIZATION|AVAILABILITY)$")

    @field_validator("question","source","source_ref")
    @classmethod
    def normalize(cls,value):return clean(value)

class ContactInput(StrictModel):
    name:str=Field(min_length=1,max_length=200)
    employer:str=Field(min_length=1,max_length=200)
    email:str|None=Field(default=None,max_length=320,pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    source_url:str|None=Field(default=None,max_length=2000)
    source_message_id:str|None=Field(default=None,max_length=500)
    role_relevance:str=Field(min_length=1,max_length=1000)
    verification_status:str=Field(pattern="^(VERIFIED|UNVERIFIED|NO_REPLY)$")

class DraftRequest(StrictModel):
    authorization_id:str|None=Field(default=None,pattern=r'^[0-9a-f]{32}$')
    contact_id:str=Field(min_length=1,max_length=100)
    intent:str=Field(default="NEW_APPLICATION",pattern="^(NEW_APPLICATION|RECRUITER_REPLY)$")
    received_message_id:str|None=Field(default=None,max_length=500)

class DraftResolution(StrictModel):
    outcome:str=Field(pattern="^(SAVED|NO_DRAFT)$")
    gmail_draft_id:str|None=Field(default=None,max_length=500)
