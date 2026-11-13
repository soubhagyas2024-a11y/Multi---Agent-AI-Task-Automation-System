import pytest

from agents import planner, verifier
from automation import code_execution
from utils.helpers import safe_join, extract_json
from utils.validators import validate_upload, validate_password


def test_planner_validation_and_fallback():
    obj, subs = planner.validate_plan({"subtasks": [{"id": "a", "agent": "writer", "description": "x", "depends_on": ["zzz"]}]}, ["writer"])
    assert subs[0]["depends_on"] == []
    with pytest.raises(ValueError):
        planner.validate_plan({"subtasks": [{"id": "a", "agent": "hacker", "description": "x"}]}, ["writer"])
    _, subs = planner.heuristic_plan("research the latest AI news and write a report", [], ["researcher", "writer"])
    assert [s["agent"] for s in subs] == ["researcher", "writer"] and subs[1]["depends_on"] == ["t1"]


def test_verifier_flags_failures():
    res = verifier.verify({"subtasks": [{"id": "t1", "agent": "writer", "status": "failed", "result": "boom", "depends_on": []}], "artifacts": []})
    assert not res["passed"] and res["retry"] == ["t1"]


def test_code_sandbox_blocks_dangerous_code(tmp_path):
    for bad in ("import os", "open('x')", "().__class__", "__import__('os')", "import subprocess"):
        with pytest.raises(ValueError):
            code_execution.validate_code(bad)
    assert code_execution.run_python("print(sum(range(5)))", tmp_path)["stdout"].strip() == "10"


def test_path_traversal_and_uploads(tmp_path):
    with pytest.raises(PermissionError):
        safe_join(tmp_path, "../../etc/passwd")
    with pytest.raises(ValueError):
        validate_upload("evil.exe", b"MZ")
    with pytest.raises(ValueError):
        validate_upload("fake.pdf", b"not a pdf")
    assert validate_upload("../../a b.csv", b"x,y\n1,2") == "a_b.csv"
    with pytest.raises(ValueError):
        validate_password("short")
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
