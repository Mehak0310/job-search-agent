"""M2D state models. Imported text is evidence, never instructions."""
from enum import StrEnum
from pydantic import Field
from .models import StrictModel

class Stream(StrEnum):
    MAJOR="MAJOR";SPECIALIST="SPECIALIST";REMOTE="REMOTE";GMAIL="GMAIL";PIPELINE="PIPELINE"
class ImplementationState(StrEnum):
    IMPLEMENTED_LIVE_VERIFIED="IMPLEMENTED_LIVE_VERIFIED";FIXTURE_TESTED="FIXTURE_TESTED";MANUAL_IMPORT_ONLY="MANUAL_IMPORT_ONLY";ACCESS_BLOCKED="ACCESS_BLOCKED";NOT_IMPLEMENTED="NOT_IMPLEMENTED"
class CoverageStatus(StrEnum):
    UNATTEMPTED="UNATTEMPTED";ATTEMPTED_NO_USABLE_RESULTS="ATTEMPTED_NO_USABLE_RESULTS";PARTIALLY_SEARCHED="PARTIALLY_SEARCHED";MEANINGFULLY_SEARCHED="MEANINGFULLY_SEARCHED";EXHAUSTIVELY_SEARCHED="EXHAUSTIVELY_SEARCHED";ACCESS_BLOCKED="ACCESS_BLOCKED"
class Readiness(StrEnum):
    FULLY_VERIFIED_APPLICATION_READY="FULLY_VERIFIED_APPLICATION_READY";READY_FOR_PORTAL_REVIEW="READY_FOR_PORTAL_REVIEW";EMAIL_DRAFT_READY="EMAIL_DRAFT_READY";PROMISING_NEEDS_VERIFICATION="PROMISING_NEEDS_VERIFICATION";EXCLUDED="EXCLUDED"
class TriState(StrEnum): PASS="PASS";FAIL="FAIL";UNKNOWN="UNKNOWN";CONFLICT="CONFLICT"

class OperationalFacts(StrictModel):
    active:TriState=TriState.UNKNOWN
    india_eligible:TriState=TriState.UNKNOWN
    headcount:TriState=TriState.UNKNOWN
    direct_permanent_payroll:TriState=TriState.UNKNOWN
    mandatory_requirements:TriState=TriState.UNKNOWN
    verified_recipient:TriState=TriState.UNKNOWN
    work_mode:str=Field(default="unknown",pattern="^(onsite|hybrid|remote|unknown)$")

class EmailExportMessage(StrictModel):
    message_id:str=Field(min_length=1,max_length=500)
    thread_id:str|None=Field(default=None,max_length=500)
    received_at:str
    labels:list[str]=Field(default_factory=list,max_length=100)
    mailbox:str=Field(default="received",pattern="^(received|sent|draft)$")
    subject:str=Field(default="",max_length=1000)
    sender_domain:str|None=Field(default=None,max_length=253)
    sender:str|None=Field(default=None,max_length=1000)
    body:str=Field(default="",max_length=200000)
    cursor:str|None=Field(default=None,max_length=500)

class JobQueueImportRow(StrictModel):
    job_key:str=Field(min_length=1,max_length=128)
    company:str=Field(min_length=1,max_length=300)
    title:str=Field(min_length=1,max_length=300)
    exact_vacancy_url:str=Field(min_length=8,max_length=2000)
    imported_status_claim:str|None=Field(default=None,max_length=100)
