import json

import pytest

from routeiq.cascade import RouteResult
from routeiq.integrations import build_target
from routeiq.integrations.base import make_record
from routeiq.integrations.jsonl import JsonlExport


def read_lines(path):
    return path.read_text(encoding="utf-8").splitlines()


def test_jsonl_appends_one_line_per_record(tmp_path):
    path = tmp_path / "out.jsonl"
    export = JsonlExport(path)
    first = {"request_id": 1, "label": "a"}
    second = {"request_id": 2, "label": "b"}
    export.send(first)
    export.send(second)
    lines = read_lines(path)
    assert len(lines) == 2
    assert json.loads(lines[0]) == first
    assert json.loads(lines[1]) == second


def test_jsonl_keeps_non_ascii_characters(tmp_path):
    path = tmp_path / "out.jsonl"
    JsonlExport(path).send({"text": "kartım çalındı"})
    raw = path.read_text(encoding="utf-8")
    assert "çalındı" in raw
    assert "\\u00e7" not in raw


def test_jsonl_creates_missing_directories(tmp_path):
    path = tmp_path / "a" / "b" / "out.jsonl"
    JsonlExport(path).send({"request_id": 1})
    assert path.exists()


def test_jsonl_does_not_overwrite_existing_file(tmp_path):
    path = tmp_path / "out.jsonl"
    JsonlExport(path).send({"request_id": 1})
    JsonlExport(path).send({"request_id": 2})
    assert len(read_lines(path)) == 2


def test_build_target_without_target_returns_none():
    assert build_target({}) is None


def test_build_target_none_type_returns_none():
    assert build_target({"target": {"type": "none"}}) is None


def test_build_target_jsonl(tmp_path):
    config = {"target": {"type": "jsonl", "path": str(tmp_path / "x.jsonl")}}
    assert isinstance(build_target(config), JsonlExport)


def test_build_target_unknown_type_raises():
    with pytest.raises(ValueError):
        build_target({"target": {"type": "zzz"}})


def test_make_record_copies_result_fields():
    result = RouteResult("card_declined", 0.7, "baseline", "accepted", 0.0, 12.0)
    record = make_record(5, "my card got declined", result, "cascade")
    assert record == {
        "request_id": 5,
        "text": "my card got declined",
        "label": "card_declined",
        "confidence": 0.7,
        "tier": "baseline",
        "source": "cascade",
    }
