# Security and future approval design

Do not expose the server publicly. No accounts, credentials, tokens, cookies, paid services, CAPTCHA bypass, or scraping in this milestone. Ignore local data and secrets in Git. Treat imports as untrusted, allow only HTTP(S) application URLs without user-info, reject sensitive URL query keys, and restrict field sizes and upload volume. Errors/audit store codes, counts, IDs and statuses, not input content.

Future application packages must be immutable snapshots containing canonical job version, exact resume/document content hashes, material answers, target portal and candidate identity. Compute a canonical SHA-256 digest. Explicit user approval must name that exact digest, target and expiry. Execution rechecks digest, expiry, single-use approval and package state transactionally. Any job, resume, document or material answer change invalidates approval; denial/revocation/consumption is audited. UI status APPROVED is a manual label and never an authorization grant. SUBMITTED is also manual and carries `submission_verified=false`.

Milestone 1 implements a pure package-fingerprint utility and invariant tests only. It exposes no approval or submission endpoint. Future approval storage, token issuance and submission adapters are deferred.

## Milestone 2A public discovery safeguards

Only public published-listing GET endpoints on fixed HTTPS Greenhouse and Lever global/EU hosts. No redirects, private ATS APIs, application questions/forms, credentials, account access or submission requests. Disable ambient proxy environment inheritance and use bounded timeouts, responses, request counts, cooldowns and runtime. Honor Retry-After; do not evade access denials or rate limits. Uploaded/configured source identifiers cannot introduce an arbitrary host or URL.

Job HTML is entity-decoded and stripped to plain text; script/style contents are discarded and frontend uses textContent. External listing/apply links are validated and opened with noopener/noreferrer. Raw descriptions, exception strings and opaque input contents do not enter audit/events. Public snapshots are local data in ignored data/, not Git.

Migration backup and rollback retain user statuses and append-only history. Registry enable/disable is a local preference. Background discovery uses the same origin/host defenses as file mutations. Neither APPROVED nor SUBMITTED labels grant permission or evidence of submission.

The schedule defaults to preview only. Actual task registration requires explicit user approval and --register. Use least privilege, interactive logged-in user context and no stored passwords. Existing unrelated task names are never forcibly overwritten. PowerShell execution policy was not changed; a native Python/XML/schtasks implementation provides the supported alternative. No persistent task was registered during implementation. Paid services, PRs and real application execution remain separately gated.


## Milestone 2A.1 boundaries
Source verification and discovery use public HTTPS GET endpoints only, strict hosts, response/request/runtime budgets and sanitized text. Browser QA uses installed Chrome with an isolated temporary profile. No accounts, application actions, scheduler registration, security changes or persistent browser profile are permitted.


## Multi-platform boundary
Only documented anonymous Remote OK JSON and WWR RSS are fetched. WWR attribution links are preserved. Restricted/authenticated platforms are represented as matrix decisions and accept only manual/user-provided imports; the agent does not crawl them or access email. URL import remains metadata-only unless a host is explicitly permitted.
