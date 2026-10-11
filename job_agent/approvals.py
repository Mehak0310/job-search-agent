"""Future authorization primitive, not a grant or submission implementation."""
import hashlib
import json


def package_fingerprint(*, job: dict, resume_hash: str, document_hashes: list[str], answers: dict, target: str, candidate_id: str) -> str:
    snapshot = {"job": job, "resume_hash": resume_hash, "document_hashes": document_hashes, "answers": answers, "target": target, "candidate_id": candidate_id}
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
