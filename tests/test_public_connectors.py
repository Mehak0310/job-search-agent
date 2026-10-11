from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from job_agent.discovery_models import DiscoverySettings, SourceConfig, metrics
from job_agent.public_connectors import GreenhouseConnector, LeverConnector, ProviderError, PublicReader, RequestBudget, plain_text, retry_delay


@pytest.fixture
def greenhouse_record():
    return {"id": 123, "title": "Frontend Technical Lead", "location": {"name": "Bengaluru, India (Hybrid)"}, "absolute_url": "https://example.com/jobs/123", "content": "<h3>Requirements</h3><p>React and TypeScript required.</p><p>5+ years of professional experience</p>", "updated_at": "2026-10-01T00:00:00Z"}


@pytest.fixture
def lever_record(greenhouse_record):
    return {"id": "abc", "text": greenhouse_record["title"], "categories": {"location": greenhouse_record["location"]["name"]}, "descriptionPlain": "Requirements\nReact and TypeScript required.\n5+ years of professional experience", "hostedUrl": greenhouse_record["absolute_url"], "applyUrl": greenhouse_record["absolute_url"], "workplaceType": "hybrid"}


def reader(handler, **settings):
    counters = metrics()
    budget = RequestBudget(DiscoverySettings(**settings), sleep=lambda _: None)
    return PublicReader(httpx.Client(transport=httpx.MockTransport(handler)), budget, counters)


def test_greenhouse_parse_and_whole_board(greenhouse_record):
    def handler(request):
        assert request.method == "GET" and request.url.params["content"] == "true"
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"jobs": [greenhouse_record], "meta": {"total": 1}}, headers={"ETag": "one", "Cache-Control": "max-age=60"})
    r = reader(handler)
    source = SourceConfig(id="gh", provider="greenhouse", company="Acme", board="acme")
    connector = GreenhouseConnector()
    batch = connector.fetch(source, r, {})
    job, link, evidence = connector.normalize(source, batch.records[0])
    assert job.source_job_id == "123" and job.work_mode == "hybrid"
    assert evidence["required"] == ["react", "typescript"] and evidence["experience"]["min"] == 5
    assert batch.checkpoint["pages"] == 1 and batch.checkpoint["etag"] == "one"
    assert r.counters["requests"] == 1 and link.startswith("https://")


def test_lever_pagination_and_eu(lever_record):
    seen = []
    def handler(request):
        seen.append(request)
        assert request.url.host == "api.eu.lever.co"
        assert request.url.params["mode"] == "json"
        skip = int(request.url.params["skip"])
        return httpx.Response(200, json=[lever_record | {"id": str(skip)}] if skip < 2 else [])
    r = reader(handler, page_size=1)
    source = SourceConfig(id="lever", provider="lever", company="Acme", board="acme", region="eu")
    batch = LeverConnector().fetch(source, r, {})
    assert len(batch.records) == 2 and batch.checkpoint["pages"] == 3
    assert [int(req.url.params["skip"]) for req in seen] == [0, 1, 2]
    job, _, evidence = LeverConnector().normalize(source, lever_record | {"country": "in", "lists": [{"text": "Preferred", "content": "<li>Python</li>"}], "additional": "<p>About us</p>"})
    assert job.work_mode == "hybrid" and evidence["country"] == "IN" and "python" in evidence["preferred"]


@pytest.mark.parametrize("provider,checkpoint", [(GreenhouseConnector, {"complete": True, "etag": "one"}), (LeverConnector, {"complete": True, "etag": "one", "pages": 1})])
def test_conditional_caching(provider, checkpoint):
    def handler(request):
        assert request.headers["if-none-match"] == "one"
        return httpx.Response(304)
    batch = provider().fetch(SourceConfig(id="a", provider="greenhouse" if provider is GreenhouseConnector else "lever", company="Acme", board="acme"), reader(handler), checkpoint)
    assert batch.not_modified


@pytest.mark.parametrize("provider,data,code", [(GreenhouseConnector, [], "invalid_board_response"), (GreenhouseConnector, {"jobs": [], "meta": {"total": 10}}, "incomplete_board_response"), (GreenhouseConnector, {"jobs": [{}, {}]}, "record_limit_exceeded"), (LeverConnector, {}, "invalid_board_response"), (LeverConnector, [{}, {}], "record_limit_exceeded")])
def test_bad_board_responses(provider, data, code):
    r = reader(lambda req: httpx.Response(200, json=data), max_records=1)
    with pytest.raises(ProviderError, match=code):
        provider().fetch(SourceConfig(id="a", provider="greenhouse", company="Acme", board="acme"), r, {})


@pytest.mark.parametrize("provider,checkpoint", [(GreenhouseConnector, {}), (LeverConnector, {})])
def test_unexpected_304(provider, checkpoint):
    with pytest.raises(ProviderError, match="unexpected_not_modified"):
        provider().fetch(SourceConfig(id="a", provider="greenhouse", company="Acme", board="acme"), reader(lambda _: httpx.Response(304)), checkpoint)


def test_repeated_lever_page(lever_record):
    with pytest.raises(ProviderError, match="repeated_page_or_id"):
        LeverConnector().fetch(SourceConfig(id="a", provider="lever", company="Acme", board="acme"), reader(lambda _: httpx.Response(200, json=[lever_record]), page_size=1), {})


@pytest.mark.parametrize("status,code", [(404, "board_not_found"), (403, "access_denied"), (401, "access_denied"), (302, "unexpected_http_status"), (429, "rate_limited"), (503, "transient_http_error")])
def test_http_errors(status, code):
    r = reader(lambda _: httpx.Response(status, headers={"retry-after": "9999"}), retry_limit=1)
    with pytest.raises(ProviderError, match=code):
        r.get("https://api.lever.co/v0/postings/acme", {})
    assert r.counters["http_errors"] >= 1
    if status == 429:
        assert r.counters["requests"] == 1  # Never retry earlier than provider's requested delay.


@pytest.mark.parametrize("exception,code", [(httpx.ReadTimeout, "request_timeout"), (httpx.ConnectError, "network_error")])
def test_transport_retries(exception, code):
    def handler(request):
        raise exception("secret remote data", request=request)
    r = reader(handler, retry_limit=1)
    with pytest.raises(ProviderError, match=code):
        r.get("https://api.lever.co/v0/postings/acme", {})
    assert r.counters["requests"] == 2 and r.counters["retries"] == 1


def test_retry_recovers_and_honors_delay():
    calls, delays = [], []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "2"}) if len(calls) == 1 else httpx.Response(200, json=[])
    r = reader(handler)
    r.budget.sleep = delays.append
    assert r.get("https://api.lever.co/v0/postings/acme", {})[0] == []
    assert delays == [2] and r.counters["retries"] == 1


def test_transient_http_backoff_then_success():
    calls, delays = [], []
    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json=[])
    r = reader(handler)
    r.budget.sleep = delays.append
    assert r.get("https://api.lever.co/v0/postings/acme", {})[0] == []
    assert delays == [1]


@pytest.mark.parametrize("url", ["http://api.lever.co/x", "https://evil.example/x", "https://user@api.lever.co/x", "https://api.lever.co:8443/x"])
def test_endpoint_allowlist(url):
    with pytest.raises(ProviderError, match="unsafe_endpoint"):
        reader(lambda _: httpx.Response(200, json=[])).get(url, {})


@pytest.mark.parametrize("content,headers,code", [(b"{", {}, "malformed_response"), (b"{}", {"content-length": "abc"}, "invalid_response_length"), (b"x" * 1025, {"content-length": "0"}, "response_too_large"), (b"{}", {"content-length": "1025"}, "response_too_large")])
def test_response_limits_and_malformed(content, headers, code):
    r = reader(lambda _: httpx.Response(200, content=content, headers=headers), max_response_bytes=1024)
    with pytest.raises(ProviderError, match=code):
        r.get("https://api.lever.co/v0/postings/acme", {})


def test_budgets():
    budget = RequestBudget(DiscoverySettings(max_requests=1))
    budget.request()
    with pytest.raises(ProviderError, match="request_budget_exhausted"):
        budget.request()
    budget.deadline = 0
    with pytest.raises(ProviderError, match="runtime_budget_exhausted"):
        budget.check()


def test_plain_text_and_retry_headers():
    assert plain_text('&lt;p&gt;Hello&lt;/p&gt;<script>do not run</script><style>css</style><div>World<br>Next</div>') == "Hello\nWorld\nNext"
    with pytest.raises(ValueError):
        plain_text(None)
    assert retry_delay("4") == 4 and retry_delay("invalid") == 60 and retry_delay(None) == 60
    assert retry_delay(format_datetime(datetime.now(timezone.utc) + timedelta(seconds=60))) > 50
    assert retry_delay("-1") == 60


@pytest.mark.parametrize("change", [{"id": True}, {"absolute_url": "http://example.com"}, {"location": {}}, {"content": 42}])
def test_greenhouse_invalid_record(greenhouse_record, change):
    with pytest.raises((ValueError, KeyError)):
        GreenhouseConnector().normalize(SourceConfig(id="a", provider="greenhouse", company="Acme", board="acme"), greenhouse_record | change)


@pytest.mark.parametrize("change", [{"categories": {"allLocations": [42]}}, {"hostedUrl": "http://example.com"}, {"applyUrl": "http://example.com"}, {"text": ""}])
def test_lever_invalid_record(lever_record, change):
    with pytest.raises(ValueError):
        LeverConnector().normalize(SourceConfig(id="a", provider="lever", company="Acme", board="acme"), lever_record | change)
