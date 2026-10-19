"""UTC publication parsing, location normalization, and separate freshness priority."""
import re
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from .models import key

ALIASES={"js":"javascript","ts":"typescript","react.js":"react","reactjs":"react","angular framework":"angular","c sharp":"c#"}
WINDOWS={"1h":1,"6h":6,"12h":12,"24h":24,"48h":48,"7d":168}

def utc_timestamp(value):
    if value in (None,""): return None,"UNKNOWN"
    try:
        if isinstance(value,(int,float)):
            stamp=datetime.fromtimestamp(value/1000 if value>10_000_000_000 else value,tz=timezone.utc); confidence="HIGH"
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}",str(value)):
            stamp=datetime.combine(date.fromisoformat(str(value)),datetime.min.time(),tzinfo=timezone.utc); confidence="DATE_ONLY"
        else:
            try: stamp=datetime.fromisoformat(str(value).replace("Z","+00:00"))
            except ValueError: stamp=parsedate_to_datetime(str(value))
            if stamp.tzinfo is None: stamp=stamp.replace(tzinfo=timezone.utc)
            stamp=stamp.astimezone(timezone.utc); confidence="HIGH"
        if stamp>datetime.now(timezone.utc): return None,"INVALID_FUTURE"
        return stamp.isoformat(),confidence
    except (ValueError,TypeError,OverflowError,OSError): return None,"INVALID"

def age_hours(published_at,now=None):
    if not published_at:return None
    now=now or datetime.now(timezone.utc); stamp=datetime.fromisoformat(published_at)
    return max(0,(now-stamp).total_seconds()/3600)

def freshness_weight(hours):
    if hours is None:return 0
    for boundary,weight in ((1,1),(6,.98),(12,.95),(24,.9),(48,.8),(168,.6)):
        if hours<boundary:return weight
    return .35

def discovery_priority(score,eligibility,published_at,now=None):
    return round(score*.7 + freshness_weight(age_hours(published_at,now))*20 + {"ELIGIBLE":10,"UNKNOWN":3,"INELIGIBLE":0}[eligibility],3)

def location_bucket(location,eligibility="UNKNOWN",work_mode="unknown"):
    value=key(location or '')
    if work_mode=="remote" and eligibility=="ELIGIBLE":return "REMOTE_INDIA"
    if re.search(r"\bgreater noida\b",value):return "GREATER_NOIDA"
    if re.search(r"\bnoida\b",value):return "NOIDA"
    if re.search(r"\b(gurgaon|gurugram)\b",value):return "GURUGRAM"
    if re.search(r"\b(chandigarh)\b",value):return "CHANDIGARH"
    if re.search(r"\b(mohali|sas nagar)\b",value):return "MOHALI"
    if re.search(r"\b(delhi|new delhi|ghaziabad|faridabad)\b",value):return "DELHI_NCR"
    if eligibility=="ELIGIBLE":return "OTHER_INDIA"
    return "UNKNOWN"

def normalize_skills(values): return sorted({ALIASES.get(key(v),key(v)) for v in values if key(v)})
