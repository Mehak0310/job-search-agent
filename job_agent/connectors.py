"""Bounded file connector. Portal access is intentionally unimplemented."""
import csv
import io
import json
from typing import Protocol

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1000


class ImportProblem(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class SourceConnector(Protocol):
    def read(self, payload: bytes, format: str) -> list[dict]: ...


class FileConnector:
    def read(self, payload: bytes, format: str) -> list[dict]:
        if len(payload) > MAX_BYTES:
            raise ImportProblem("file_too_large")
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ImportProblem("invalid_utf8") from None
        if not text.strip():
            raise ImportProblem("empty_file")
        try:
            if format == "json":
                rows = json.loads(text)
                if not isinstance(rows, list):
                    raise ImportProblem("json_array_required")
            elif format == "csv":
                reader = csv.DictReader(io.StringIO(text), strict=True)
                headers = reader.fieldnames
                if not headers or len(set(headers)) != len(headers) or not {"source", "company", "title", "location"}.issubset(headers):
                    raise ImportProblem("invalid_csv_headers")
                rows = []
                for row in reader:
                    if None in row or any(v is None for v in row.values()):
                        raise ImportProblem("invalid_csv_columns")
                    if "skills" in row:
                        row["skills"] = [s for s in row["skills"].split(";") if s.strip()]
                    for optional in ("source_job_id", "application_url", "min_experience", "max_experience", "work_mode", "is_sample"):
                        if row.get(optional) == "":
                            del row[optional]
                    rows.append(row)
                    if len(rows) > MAX_ROWS:
                        raise ImportProblem("too_many_records")
            else:
                raise ImportProblem("unsupported_format")
        except (json.JSONDecodeError, csv.Error, RecursionError):
            raise ImportProblem("malformed_document") from None
        if len(rows) > MAX_ROWS:
            raise ImportProblem("too_many_records")
        return rows
