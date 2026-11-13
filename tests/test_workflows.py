import pytest

from workflows import workflow_builder as wb
from workflows.routing import propagate, ready


def test_cycle_and_unknown_agent_rejected():
    with pytest.raises(ValueError):
        wb.validate({"nodes": [{"id": "a", "agent": "writer", "depends_on": ["b"]}, {"id": "b", "agent": "writer", "depends_on": ["a"]}]})
    with pytest.raises(ValueError):
        wb.validate({"nodes": [{"id": "a", "agent": "planner"}]})


def test_sequential_chaining_and_routing():
    subs = wb.to_subtasks({"workflow_type": "sequential", "nodes": [{"id": "a", "agent": "researcher"}, {"id": "b", "agent": "writer"}]})
    assert subs[1]["depends_on"] == ["a"]
    assert [s["id"] for s in ready(subs)] == ["a"]
    subs[0]["status"] = "failed"
    assert propagate(subs)[1]["status"] == "blocked"
