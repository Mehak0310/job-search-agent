import json

import pytest

from job_agent.connectors import FileConnector, ImportProblem, MAX_BYTES


@pytest.mark.parametrize("payload,format,code", [(b"", "json", "empty_file"), (b"\xff", "json", "invalid_utf8"), (b"{", "json", "malformed_document"), (b"{}", "json", "json_array_required"), (b"[]", "xml", "unsupported_format"), (b"source,source\na,b", "csv", "invalid_csv_headers"), (b"source,company,title,location\na,b,c", "csv", "invalid_csv_columns"), (b"source,company,title,location\na,b,c,d,e", "csv", "invalid_csv_columns"), (b'source,company,title,location\n"unterminated', "csv", "malformed_document"), (b"x" * (MAX_BYTES + 1), "json", "file_too_large"), (json.dumps([{}] * 1001).encode(), "json", "too_many_records"), (("source,company,title,location\n" + "a,b,c,d\n" * 1001).encode(), "csv", "too_many_records")], ids=lambda value: 'payload-' + str(len(value)) if isinstance(value, bytes) else None)
def test_parse_failures(payload, format, code):
    with pytest.raises(ImportProblem) as error:
        FileConnector().read(payload, format)
    assert error.value.code == code


def test_csv_optional_values_and_bom():
    rows = FileConnector().read(b'\xef\xbb\xbfsource,company,title,location,skills,application_url,min_experience,work_mode,is_sample\na,b,c,d,Python;React,,,,', "csv")
    assert rows == [{"source": "a", "company": "b", "title": "c", "location": "d", "skills": ["Python", "React"]}]


def test_json_valid(record):
    assert FileConnector().read(json.dumps([record]).encode(), "json") == [record]
