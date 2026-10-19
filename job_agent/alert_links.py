"""Local parsing only; imported HTML and text never trigger network access."""
from html.parser import HTMLParser
import re


class AlertLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links=[];self.current=None

    def handle_starttag(self,tag,attrs):
        if tag=='a':
            href=dict(attrs).get('href')
            self.current=[href,[]] if href else None

    def handle_data(self,data):
        if self.current:self.current[1].append(data)

    def handle_endtag(self,tag):
        if tag=='a' and self.current:
            self.links.append({'url':self.current[0],'title':' '.join(self.current[1]),'text_parts':[s.strip() for s in self.current[1] if s.strip()]});self.current=None


def alert_links(body,subject):
    parser=AlertLinks();parser.feed(body);parser.close()
    links=parser.links
    # Exact URL validation is separate and host-aware. Never follow redirect links.
    links.extend({'url':match.group().rstrip('.,);]'),'title':subject if '<a' not in body.lower() else ''} for match in re.finditer(r'https://[^\s<>"\']+',body))
    return links
