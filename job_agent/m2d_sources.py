"""Reviewed M2D source and employer requirements; entries do not imply coverage."""
from .m2d_models import Stream,ImplementationState

def source(source_id,name,stream,url,state,owner=None,connector=None,time=None):
    return dict(source_id=source_id,display_name=name,stream=stream.value,owner=owner or stream.value,official_url=url,implementation_state=state.value,connector=connector,reference_time_ist=time)

SOURCES=[
 source("linkedin","LinkedIn Jobs",Stream.MAJOR,"https://www.linkedin.com/jobs/",ImplementationState.MANUAL_IMPORT_ONLY,time="09:55"),
 source("naukri","Naukri",Stream.MAJOR,"https://www.naukri.com/",ImplementationState.MANUAL_IMPORT_ONLY,time="09:55"),
 source("indeed","Indeed",Stream.MAJOR,"https://www.indeed.com/",ImplementationState.MANUAL_IMPORT_ONLY,time="09:55"),
 source("glassdoor","Glassdoor",Stream.MAJOR,"https://www.glassdoor.com/Job/",ImplementationState.MANUAL_IMPORT_ONLY,time="09:55"),
 source("foundit","Foundit",Stream.MAJOR,"https://www.foundit.in/",ImplementationState.MANUAL_IMPORT_ONLY,time="09:55"),
 source("employer-careers","Official employer career sites",Stream.MAJOR,None,ImplementationState.MANUAL_IMPORT_ONLY,time="09:55"),
 source("greenhouse","Employer-hosted Greenhouse",Stream.MAJOR,"https://boards.greenhouse.io/",ImplementationState.IMPLEMENTED_LIVE_VERIFIED,connector="greenhouse",time="09:55"),
 source("smartrecruiters","Employer-hosted SmartRecruiters",Stream.MAJOR,"https://careers.smartrecruiters.com/",ImplementationState.IMPLEMENTED_LIVE_VERIFIED,connector="smartrecruiters",time="09:55"),
 source("lever","Employer-hosted Lever",Stream.MAJOR,"https://jobs.lever.co/",ImplementationState.IMPLEMENTED_LIVE_VERIFIED,connector="lever",time="09:55"),
 source("hirist","Hirist",Stream.SPECIALIST,"https://www.hirist.tech/",ImplementationState.MANUAL_IMPORT_ONLY,time="10:00"),
 source("instahyre","Instahyre",Stream.SPECIALIST,"https://www.instahyre.com/",ImplementationState.MANUAL_IMPORT_ONLY,time="10:00"),
 source("cutshort","Cutshort",Stream.SPECIALIST,"https://cutshort.io/jobs",ImplementationState.MANUAL_IMPORT_ONLY,time="10:00"),
 source("hackerearth","HackerEarth Jobs",Stream.SPECIALIST,"https://www.hackerearth.com/recruit/",ImplementationState.MANUAL_IMPORT_ONLY,time="10:00"),
 source("weekday","Weekday",Stream.SPECIALIST,"https://www.weekday.works/",ImplementationState.NOT_IMPLEMENTED,time="10:00"),
 source("wellfound","Wellfound",Stream.SPECIALIST,"https://wellfound.com/jobs",ImplementationState.MANUAL_IMPORT_ONLY,time="10:00"),
 source("yc-jobs","YC Work at a Startup",Stream.SPECIALIST,"https://www.ycombinator.com/jobs",ImplementationState.MANUAL_IMPORT_ONLY,time="10:00"),
 source("welcome-jungle","Welcome to the Jungle",Stream.SPECIALIST,"https://www.welcometothejungle.com/en/jobs",ImplementationState.MANUAL_IMPORT_ONLY,time="10:00"),
 source("hirect","Hirect India",Stream.SPECIALIST,"https://hirect.in/",ImplementationState.MANUAL_IMPORT_ONLY,time="10:00"),
 source("upraised","Upraised",Stream.SPECIALIST,"https://jobs.upraised.co/",ImplementationState.NOT_IMPLEMENTED,time="10:00"),
 source("iimjobs","IIMJobs",Stream.SPECIALIST,"https://www.iimjobs.com/",ImplementationState.MANUAL_IMPORT_ONLY,time="10:00"),
 source("remoteok","Remote OK",Stream.REMOTE,"https://remoteok.com/",ImplementationState.IMPLEMENTED_LIVE_VERIFIED,connector="remoteok",time="10:30"),
 source("wwr","We Work Remotely",Stream.REMOTE,"https://weworkremotely.com/",ImplementationState.IMPLEMENTED_LIVE_VERIFIED,connector="wwr",time="10:30"),
 source("flexjobs","FlexJobs paid access excluded",Stream.REMOTE,"https://www.flexjobs.com/",ImplementationState.ACCESS_BLOCKED,time="10:30"),
 source("turing","Turing direct-employer permanent roles",Stream.REMOTE,"https://www.turing.com/jobs",ImplementationState.MANUAL_IMPORT_ONLY,time="10:30"),
 source("dice","Dice",Stream.REMOTE,"https://www.dice.com/",ImplementationState.MANUAL_IMPORT_ONLY,time="10:30"),
 source("remote-employer-careers","Remote-first employer official careers",Stream.REMOTE,None,ImplementationState.MANUAL_IMPORT_ONLY,time="10:30"),
 source("gmail","Received Gmail job messages",Stream.GMAIL,None,ImplementationState.ACCESS_BLOCKED,time="10:20"),
 source("pipeline-handoff","Application Pipeline Stages 3-5",Stream.PIPELINE,None,ImplementationState.FIXTURE_TESTED,time="11:30"),
]

PRIORITY_EMPLOYERS=("Adobe","Google","Microsoft","Amazon","Flipkart","Uber","Airtel","Goldman Sachs","Optum/UHG","McKinsey/QuantumBlack","Bain","Deloitte","PwC","KPMG","ZS","Accenture","L&T/LTIMindtree/Mindtree","Publicis Sapient","Thoughtworks","Nagarro","EPAM","Capgemini","Cognizant","HCLTech","TCS","IBM","Salesforce","McAfee","ServiceNow","SAP","Oracle","Atlassian")

SOURCE_DIAGNOSTICS={item["source_id"]:{
 "access_method":"public_get_adapter" if item["connector"] else "received_mail_oauth" if item["source_id"]=="gmail" else "manual_or_alert_import" if item["implementation_state"]=="MANUAL_IMPORT_ONLY" else "not_implemented" if item["implementation_state"]=="NOT_IMPLEMENTED" else "paid_or_restricted",
 "endpoint":item["official_url"],
 "root_cause":"paid_access_excluded" if item["source_id"]=="flexjobs" else None if item["source_id"]=="gmail" or item["connector"] else "adapter_not_implemented",
 "fallback":"official_employer_careers_or_received_alert_import" if item["stream"] in {"MAJOR","SPECIALIST"} else "received_export_or_official_employer_careers",
 "retest":"live_interval_verified_2026-10-15" if item["source_id"]=="gmail" else "live_verified_2026-10-14" if item["connector"] else "not_live_tested"
} for item in SOURCES}
