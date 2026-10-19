# M3 acceptance checklist

| Criterion | Result | Evidence / limit |
|---|---|---|
| Durable versioned packets by JobKey | PASS | Schema v9 and focused tests |
| Grounded truthful text and visible gaps | PASS | Deterministic profile/JD intersection; unknown hard facts retained |
| Actual-question provenance and limits | PASS | Source reference required; character-limit test |
| Verified contacts; no guessed addresses | PASS | Verification gate requires email plus URL/message evidence |
| Known incompatible jobs blocked | PASS | Eligibility test |
| Duplicate/concurrent draft prevention | PASS | Transactional unique operation identity |
| Timeout/unknown outcome recovery | PASS | `UNCERTAIN` plus manual resolution; no blind retry |
| User edits preserve prior and Gmail versions | PASS | Immutable packet versions and operation packet-version pin |
| No send/submission path | PASS | Draft adapter has no send method; route inventory test |
| Required HTML/manual-file instructions | PASS | Packet content test |
| Dashboard and review workbook | PASS | Synthetic browser/API and XLSX validation |
| Representative actual-vacancy packets | PASS | 63 prepared; Particle41 Frontend Developer and Mindtickle AI Product Engineer reviewed as representatives |
| Live Gmail draft | BLOCKED | No local Desktop OAuth client/token or verified recipient |

Software completion can pass with the live-Gmail criterion blocked. Operational Gmail readiness remains partial until explicit local consent and a verified role recipient exist.
