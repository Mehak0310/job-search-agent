"""Bounded GET-only resolution of named vacancy tracking links, never actions."""
import hashlib
import ipaddress
import json
import socket
from datetime import datetime,timedelta,timezone
from urllib.parse import urlsplit,urljoin,unquote
import httpx
from .database import now
from .public_connectors import RequestBudget,ProviderError
from .discovery_models import DiscoverySettings

HOSTS={'engage.indeed.com','in.indeed.com','www.indeed.com','indeed.com','www.naukri.com','naukri.com','tr.naukri.com','www.glassdoor.com','www.glassdoor.co.in','postoffice.hirist.tech','www.hirist.tech','hirist.tech'}


def public_target(url,dns=socket.getaddrinfo):
    p=urlsplit(url)
    if p.scheme!='https' or p.username or p.password or p.port not in {None,443} or p.hostname not in HOSTS:raise ValueError('unsafe_redirect_destination')
    if any(term in unquote(p.path).lower() for term in ('unsubscribe','login','signin','autologin','apply','account','preferences')):raise ValueError('action_link_rejected')
    addresses=dns(p.hostname,443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):raise ValueError('non_public_redirect_destination')
    return url


class CachedAlertResolver:
    """Read prior resolution evidence without DNS or HTTP, including expired blockers."""
    def __init__(self,db):self.db=db;self.last_error=None;self.requests=0;self.cache_hits=0

    def __call__(self,url):
        with self.db.transaction() as conn:
            row=conn.execute('SELECT result_url,error_code FROM alert_url_resolutions WHERE url_hash=?',(hashlib.sha256(url.encode()).hexdigest(),)).fetchone()
        self.last_error=row['error_code'] if row else None
        if row:self.cache_hits+=1
        return row['result_url'] if row else None

    def close(self):pass


class AlertRedirectResolver:
    def __init__(self,db,client=None,budget=None,dns=socket.getaddrinfo):
        self.db=db;self.client=client or httpx.Client(trust_env=False,follow_redirects=False,timeout=8);self.owns_client=client is None
        self.budget=budget or RequestBudget(DiscoverySettings(max_requests=30,max_runtime_seconds=120,retry_limit=0));self.dns=dns;self.last_error=None;self.requests=0;self.cache_hits=0

    def __call__(self,url):
        from .alert_extraction import exact_vacancy_url,local_destination
        self.last_error=None;hashed=hashlib.sha256(url.encode()).hexdigest()
        with self.db.transaction() as conn:old=conn.execute('SELECT * FROM alert_url_resolutions WHERE url_hash=?',(hashed,)).fetchone()
        if old and (old['state']=='RESOLVED' or (old['next_retry_after'] or '')>now()):
            self.cache_hits+=1;self.last_error=old['error_code'];return old['result_url']
        result=None;code=None;current=local_destination(url)
        try:
            if not current:raise ValueError('unsafe_tracking_url')
            initial=urlsplit(current)
            if not ((initial.hostname=='engage.indeed.com' and initial.path.startswith('/f/a/')) or (initial.hostname in {'www.naukri.com','naukri.com'} and initial.path.startswith('/durl/'))):raise ValueError('unsupported_tracking_route')
            for _ in range(4):
                public_target(current,self.dns)
                exact=exact_vacancy_url(current)
                if exact:result=exact;break
                self.budget.request();self.requests+=1
                with self.client.stream('GET',current,follow_redirects=False,headers={'User-Agent':'LocalJobAgent/0.4 received-vacancy-review'},timeout=8) as response:
                    if response.status_code not in {301,302,303,307,308}:raise ValueError('tracking_http_'+str(response.status_code))
                    location=response.headers.get('location')
                    if not location:raise ValueError('redirect_without_destination')
                    current=urljoin(current,location)
            if not result:raise ValueError('redirect_hop_limit')
        except (ValueError,httpx.HTTPError,ProviderError,OSError) as error:
            code=error.code if isinstance(error,ProviderError) else str(error) if isinstance(error,ValueError) and str(error).startswith(('unsafe_','action_','non_public_','unsupported_','tracking_http_','redirect_')) else type(error).__name__
        retry=(datetime.now(timezone.utc)+timedelta(hours=6)).isoformat()
        with self.db.transaction() as conn:conn.execute('INSERT OR REPLACE INTO alert_url_resolutions VALUES(?,?,?,?,?,?)',(hashed,result,'RESOLVED' if result else 'BLOCKED',code,now(),None if result else retry))
        self.last_error=code
        return result

    def close(self):
        if self.owns_client:self.client.close()
