"""GET-only, HTTPS public board access with bounded requests and responses."""
import html
import json
import time
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx
import xml.etree.ElementTree as ET

from .classification import extract_requirements
from .discovery_models import DiscoverySettings, SourceConfig
from .models import JobInput, WorkMode, key


class ProviderError(ValueError):
    def __init__(self, code: str, retry_after: float = 0):
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "li", "br", "div", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "li", "div", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid_description")
    parser = PlainText()
    parser.feed(html.unescape(html.unescape(value)))
    return "\n".join(" ".join(line.split()) for line in "".join(parser.parts).splitlines() if line.strip())


def retry_delay(value: str | None) -> float:
    if value:
        try:
            seconds = float(value)
            if seconds >= 0 and seconds < float("inf"):
                return seconds
        except ValueError:
            pass
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            pass
    return 60


class RequestBudget:
    def __init__(self, settings: DiscoverySettings, clock=time.monotonic, sleep=time.sleep):
        self.settings, self.clock, self.sleep = settings, clock, sleep
        self.deadline = clock() + settings.max_runtime_seconds
        self.requests = 0
        self.lock = threading.Lock()

    def check(self):
        if self.clock() >= self.deadline:
            raise ProviderError("runtime_budget_exhausted")

    def request(self):
        with self.lock:
            self.check()
            if self.requests >= self.settings.max_requests:
                raise ProviderError("request_budget_exhausted")
            self.requests += 1


class PublicReader:
    HOSTS = {"boards-api.greenhouse.io", "api.lever.co", "api.eu.lever.co", "remoteok.com", "weworkremotely.com"}

    def __init__(self, client: httpx.Client, budget: RequestBudget, counters: dict):
        self.client, self.budget, self.counters = client, budget, counters

    def get(self, url: str, params: dict, headers=None, format="json") -> tuple[object, dict, bool]:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in self.HOSTS or parts.username or parts.password or parts.port not in {None, 443}:
            raise ProviderError("unsafe_endpoint")
        for attempt in range(self.budget.settings.retry_limit + 1):
            self.budget.request()
            self.counters["requests"] += 1
            delay, failure = 0, None
            try:
                timeout = min(self.budget.settings.timeout_seconds, max(0.01, self.budget.deadline - self.budget.clock()))
                with self.client.stream("GET", url, params=params, headers=headers or {}, timeout=timeout, follow_redirects=False) as response:
                    if response.status_code == 304:
                        return None, {}, True
                    if response.status_code != 200:
                        self.counters["http_errors"] += 1
                        if response.status_code == 429:
                            delay = retry_delay(response.headers.get("retry-after"))
                            failure = ProviderError("rate_limited", delay)
                        elif response.status_code in {500, 502, 503, 504}:
                            delay = retry_delay(response.headers["retry-after"]) if "retry-after" in response.headers else 2 ** attempt
                            failure = ProviderError("transient_http_error", delay)
                        else:
                            raise ProviderError("board_not_found" if response.status_code == 404 else "access_denied" if response.status_code in {401, 403} else "unexpected_http_status")
                    else:
                        try:
                            declared = int(response.headers.get("content-length", "0"))
                        except ValueError:
                            raise ProviderError("invalid_response_length") from None
                        if declared > self.budget.settings.max_response_bytes:
                            raise ProviderError("response_too_large")
                        content = bytearray()
                        for chunk in response.iter_bytes():
                            self.budget.check()
                            if len(content) + len(chunk) > self.budget.settings.max_response_bytes:
                                raise ProviderError("response_too_large")
                            content.extend(chunk)
                        self.counters["response_bytes"] += len(content)
                        try:
                            data = json.loads(content) if format == "json" else bytes(content)
                        except (ValueError, RecursionError):
                            raise ProviderError("malformed_response") from None
                        cache = {name: response.headers[name][:1024] for name in ("etag", "last-modified", "cache-control") if name in response.headers}
                        return data, cache, False
            except httpx.TimeoutException:
                failure, delay = ProviderError("request_timeout"), 2 ** attempt
            except httpx.TransportError:
                failure, delay = ProviderError("network_error"), 2 ** attempt
            if attempt == self.budget.settings.retry_limit or delay >= self.budget.deadline - self.budget.clock():
                raise failure
            self.counters["retries"] += 1
            self.budget.sleep(delay)


@dataclass
class Batch:
    records: list
    checkpoint: dict
    not_modified: bool = False


def conditional_headers(checkpoint: dict) -> dict:
    return {out: checkpoint[name] for name, out in (("etag", "If-None-Match"), ("last-modified", "If-Modified-Since")) if name in checkpoint}


class GreenhouseConnector:
    def fetch(self, source: SourceConfig, reader: PublicReader, checkpoint: dict) -> Batch:
        data, cache, unchanged = reader.get(f"https://boards-api.greenhouse.io/v1/boards/{source.board}/jobs", {"content": "true"}, conditional_headers(checkpoint))
        if unchanged:
            if not checkpoint.get("complete"):
                raise ProviderError("unexpected_not_modified")
            return Batch([], checkpoint, True)
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
            raise ProviderError("invalid_board_response")
        rows = data["jobs"]
        total = data.get("meta", {}).get("total") if isinstance(data.get("meta", {}), dict) else None
        if total is not None and total != len(rows):
            raise ProviderError("incomplete_board_response")
        if len(rows) > reader.budget.settings.max_records:
            raise ProviderError("record_limit_exceeded")
        reader.counters["records_fetched"] += len(rows)
        return Batch(rows, cache | {"complete": True, "pages": 1})

    def normalize(self, source: SourceConfig, record: dict) -> tuple[JobInput, str, dict]:
        description = plain_text(record.get("content", ""))
        location = record["location"]["name"]
        mode = "remote" if "remote" in key(location) else "hybrid" if "hybrid" in key(location) else "unknown"
        evidence = extract_requirements(description)
        evidence.update(source_updated_at=record.get("updated_at"), timestamp_provenance="greenhouse.updated_at")
        job = JobInput(source=source.id, source_job_id=str(record["id"]), company=source.company, title=record["title"], location=location, work_mode=mode, description=description, skills=evidence["mentioned"], application_url=record["absolute_url"])
        if not isinstance(record["id"], (str, int)) or isinstance(record["id"], bool) or not job.source_job_id or not job.application_url.startswith("https://"):
            raise ValueError("invalid_source_record")
        return job, job.application_url, evidence


class LeverConnector:
    def fetch(self, source: SourceConfig, reader: PublicReader, checkpoint: dict) -> Batch:
        host = "api.eu.lever.co" if source.region == "eu" else "api.lever.co"
        rows, seen, skip, pages = [], set(), 0, 0
        while True:
            headers = conditional_headers(checkpoint) if skip == 0 and checkpoint.get("pages") == 1 else {}
            data, cache, unchanged = reader.get(f"https://{host}/v0/postings/{source.board}", {"mode": "json", "skip": skip, "limit": reader.budget.settings.page_size}, headers)
            if unchanged:
                if not checkpoint.get("complete") or checkpoint.get("pages") != 1:
                    raise ProviderError("unexpected_not_modified")
                return Batch([], checkpoint, True)
            if not isinstance(data, list) or len(data) > reader.budget.settings.page_size:
                raise ProviderError("invalid_board_response")
            reader.counters["records_fetched"] += len(data)
            for record in data:
                if isinstance(record, dict) and isinstance(record.get("id"), str):
                    if record["id"] in seen:
                        raise ProviderError("repeated_page_or_id")
                    seen.add(record["id"])
            rows.extend(data)
            pages += 1
            if len(rows) > reader.budget.settings.max_records:
                raise ProviderError("record_limit_exceeded")
            if len(data) < reader.budget.settings.page_size:
                return Batch(rows, (cache if pages == 1 else {}) | {"complete": True, "pages": pages})
            skip += len(data)

    def normalize(self, source: SourceConfig, record: dict) -> tuple[JobInput, str, dict]:
        sections = [record.get("descriptionPlain") or record.get("description", "")]
        for item in record.get("lists", []):
            sections.extend([item["text"], item["content"]])
        sections.append(record.get("additionalPlain") or record.get("additional", ""))
        description = plain_text("\n".join(sections))
        categories = record["categories"]
        locations = categories.get("allLocations") or [categories["location"]]
        if not isinstance(locations, list) or any(not isinstance(s, str) for s in locations):
            raise ValueError("invalid_location")
        location = "; ".join(dict.fromkeys(locations))
        country = record.get("country")
        evidence = extract_requirements(description) | {"country": country.upper() if isinstance(country, str) else None, "published_at": record.get("createdAt"), "source_updated_at": record.get("updatedAt"), "timestamp_provenance":"lever.createdAt"}
        job = JobInput(source=source.id, source_job_id=record["id"], company=source.company, title=record["text"], location=location, work_mode={"on-site": "onsite", "remote": "remote", "hybrid": "hybrid"}.get(record.get("workplaceType"), "unknown"), description=description, skills=evidence["mentioned"], application_url=record["applyUrl"])
        listing = JobInput.safe_url(record["hostedUrl"])
        if not listing or not listing.startswith("https://") or not job.application_url.startswith("https://"):
            raise ValueError("invalid_source_url")
        return job, listing, evidence


class RemoteOKConnector:
    def fetch(self, source, reader, checkpoint):
        data,cache,unchanged=reader.get("https://remoteok.com/api",{},conditional_headers(checkpoint))
        if unchanged:return Batch([],checkpoint,True)
        if not isinstance(data,list):raise ProviderError("invalid_feed_response")
        rows=[r for r in data if isinstance(r,dict) and r.get("id")]
        if len(rows)>reader.budget.settings.max_records:raise ProviderError("record_limit_exceeded")
        reader.counters["records_fetched"]+=len(rows);return Batch(rows,cache|{"complete":True,"pages":1})
    def normalize(self,source,record):
        description=plain_text(record.get("description", "")); location=record.get("location") or "Remote"
        evidence=extract_requirements(description)|{"published_at":record.get("epoch") or record.get("date"),"timestamp_provenance":"remoteok.epoch/date"}
        url=record.get("url") or record.get("apply_url")
        job=JobInput(source=source.id,source_job_id=str(record["id"]),company=record.get("company") or "Unknown employer",title=record["position"],location=location,work_mode="remote",description=description,skills=evidence["mentioned"],application_url=url)
        return job,url,evidence

class WWRConnector:
    def fetch(self,source,reader,checkpoint):
        content,cache,unchanged=reader.get("https://weworkremotely.com/remote-jobs.rss",{},conditional_headers(checkpoint),format="xml")
        if unchanged:return Batch([],checkpoint,True)
        try: root=ET.fromstring(content)
        except ET.ParseError: raise ProviderError("invalid_feed_response") from None
        rows=[]
        for item in root.findall(".//item"):
            record={child.tag.split('}')[-1]:child.text or "" for child in item}; record["id"]=record.get("guid") or record.get("link"); rows.append(record)
        if len(rows)>reader.budget.settings.max_records:raise ProviderError("record_limit_exceeded")
        reader.counters["records_fetched"]+=len(rows);return Batch(rows,cache|{"complete":True,"pages":1})
    def normalize(self,source,record):
        title=record.get("title",""); company,sep,role=title.partition(": "); description=plain_text(record.get("description", "")); url=record.get("link")
        evidence=extract_requirements(description)|{"published_at":record.get("pubDate"),"timestamp_provenance":"rss.pubDate"}
        job=JobInput(source=source.id,source_job_id=record.get("guid") or url,company=company if sep else "Unknown employer",title=role if sep else title,location="Remote",work_mode="remote",description=description,skills=evidence["mentioned"],application_url=url)
        return job,url,evidence

CONNECTORS = {"greenhouse": GreenhouseConnector, "lever": LeverConnector, "remoteok": RemoteOKConnector, "wwr": WWRConnector}
