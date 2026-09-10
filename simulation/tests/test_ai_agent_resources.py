from simulation.fixtures import generate_agent_resources
from simulation.scenarios.ai_agent import AgentScenario


def test_calibrated_profiles_are_discoverable(tmp_path, monkeypatch):
    root = tmp_path / "agent_tasks"
    monkeypatch.setattr(generate_agent_resources, "ROOT", root)
    generate_agent_resources.generate()

    monkeypatch.setattr(AgentScenario, "AGENT_DIR", root)
    resources = AgentScenario().discover_resources()

    by_name = {resource["name"]: resource for resource in resources}
    assert set(by_name) == set(generate_agent_resources.TASKS)
    assert all(len(resource["steps"]) == 4 for resource in by_name.values())
    assert all(
        [step["type"] for step in resource["steps"]]
        == ["burst", "write", "burst", "write"]
        for resource in by_name.values()
    )

    light = sum(by_name[name]["size_bytes"] for name in ("task_light_a", "task_light_b")) / 2
    target = sum(by_name[name]["size_bytes"] for name in ("task_target_a", "task_target_b")) / 2
    heavy = sum(by_name[name]["size_bytes"] for name in ("task_heavy_a", "task_heavy_b")) / 2
    tiny = sum(by_name[name]["size_bytes"] for name in ("task_tiny_a", "task_tiny_b")) / 2
    small = sum(by_name[name]["size_bytes"] for name in ("task_small_a", "task_small_b")) / 2
    medium = sum(by_name[name]["size_bytes"] for name in ("task_medium_a", "task_medium_b")) / 2
    assert tiny < small < medium < light < target < heavy

    first_sizes = [
        step["sizes_bytes"] if step["type"] == "burst" else [step["size_bytes"]]
        for step in by_name["task_target_a"]["steps"]
    ]
    assert all(size >= 1024 for step_sizes in first_sizes for size in step_sizes)
