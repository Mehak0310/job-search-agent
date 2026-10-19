"""User-invoked local Gmail OAuth setup/status; never sends mail."""
import argparse,json
from pathlib import Path
from job_agent.gmail_local import GmailDraftAdapter,GmailOAuthReader

parser=argparse.ArgumentParser();parser.add_argument("action",choices=("status","authorize","compose-status","compose-authorize"));parser.add_argument("--client",default="data/gmail/client_secret.json");parser.add_argument("--token",default=None);args=parser.parse_args()
compose=args.action.startswith("compose-");token=Path(args.token or ("data/gmail/compose_token.json" if compose else "data/gmail/token.json"));reader=GmailDraftAdapter(Path(args.client),token) if compose else GmailOAuthReader(Path(args.client),token)
print(json.dumps(reader.authorize() if args.action.endswith("authorize") else reader.status(),indent=2))
