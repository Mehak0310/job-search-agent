"""One-shot public access diagnostics. No extraction, accounts or bypasses."""
import json
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from concurrent.futures import ThreadPoolExecutor
import httpx

from job_agent.m2d_sources import SOURCES
from job_agent.database import now


def main():
    started=time.monotonic();agent='LocalJobAgent/0.4 source-diagnostics'
    selected=[s for s in SOURCES if s['official_url'] and s['source_id'] not in {'flexjobs','greenhouse','lever','smartrecruiters','remoteok','wwr','pipeline-handoff'}]
    def diagnose(source):
        url=source['official_url'];parts=urlsplit(url)
        output={'source':source['source_id'],'url':url,'observed_at':now(),'connector':'NOT_IMPLEMENTED','requests':0}
        with httpx.Client(trust_env=False,follow_redirects=False,timeout=8,headers={'User-Agent':agent}) as client:
            try:
                robots_url=f'{parts.scheme}://{parts.netloc}/robots.txt';output['requests']+=1
                with client.stream('GET',robots_url) as response:
                    output['robots_status']=response.status_code;content=bytearray()
                    if response.status_code==200:
                        for chunk in response.iter_bytes():
                            if len(content)+len(chunk)>65536:output['termination']='robots_response_cap';return output
                            content.extend(chunk)
                        parser=RobotFileParser();parser.parse(content.decode('utf-8','replace').splitlines())
                        if not parser.can_fetch(agent,url):output['termination']='robots_disallowed';return output
                    elif response.status_code in {401,403,429}:
                        output['termination']='robots_access_restricted';return output
                output['requests']+=1
                with client.stream('GET',url) as response:
                    output['http_status']=response.status_code;output['content_type']=response.headers.get('content-type','').split(';')[0]
                    output['termination']='headers_received';output['direct_discovery']='NOT_IMPLEMENTED'
            except httpx.HTTPError as error:output['termination']=type(error).__name__
        return output
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(diagnose,selected))
    result={'started_at':now(),'runtime_seconds':round(time.monotonic()-started,3),'requests':sum(x['requests'] for x in results),
        'scope':'One-shot GET diagnostics; response headers only for pages, bounded robots reads. Not a vacancy extractor or live connector test.','sources':results}
    path=Path('data/discovery-expansion/public-access-diagnostics.json');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
