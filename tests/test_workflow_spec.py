import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "workflows" / "github-issue-to-reviewed-pr.json"
MODULE_PATH = ROOT / "module.json"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_workflow_commands_exist_in_companion_module():
    workflow = load_json(WORKFLOW_PATH)
    module = load_json(MODULE_PATH)
    module_commands = {command["id"] for command in module["commands"]}
    workflow_commands = {node["command_id"] for node in workflow["nodes"]}

    assert workflow_commands <= module_commands


def test_every_effect_requires_human_approval():
    workflow = load_json(WORKFLOW_PATH)
    effects = [node for node in workflow["nodes"] if node["type"] == "effect"]

    assert workflow["approval"] == "require_human"
    assert effects
    assert all(node.get("approval") == "require_human" for node in effects)


def test_workflow_stops_before_merge():
    workflow = load_json(WORKFLOW_PATH)
    commands = [node["command_id"] for node in workflow["nodes"]]

    assert "github.merge_pull_request" not in commands
    assert workflow["safety"]["merge_included"] is False


def test_drift_and_verification_bindings_are_present():
    workflow = load_json(WORKFLOW_PATH)
    nodes = {node["id"]: node for node in workflow["nodes"]}

    assert (
        nodes["create_work_branch"]["args"]["expected_source_sha"]
        == "{{ctx.expected_source_sha}}"
    )
    assert (
        nodes["verify_checks"]["args"]["ref"]
        == "{{nodes.write_change.commit_sha}}"
    )
    assert (
        nodes["request_reviewers"]["args"]["pull_number"]
        == "{{nodes.open_pull_request.pull_request.number}}"
    )


def test_steps_mirror_node_commands_and_templates():
    workflow = load_json(WORKFLOW_PATH)
    nodes = {node["id"]: node for node in workflow["nodes"]}
    steps = {step["id"]: step for step in workflow["steps"]}

    assert set(steps) == set(nodes)
    for node_id, node in nodes.items():
        assert steps[node_id]["command_id"] == node["command_id"]
        assert steps[node_id]["inputs_template"] == node["args"]


def test_graph_references_only_known_nodes():
    workflow = load_json(WORKFLOW_PATH)
    node_ids = {node["id"] for node in workflow["nodes"]}

    assert workflow["edges"][0] == {"from": "trigger", "to": "inspect_issue"}
    for edge in workflow["edges"]:
        assert edge["to"] in node_ids
        assert edge["from"] == "trigger" or edge["from"] in node_ids


def test_engine_spec_is_runnable_and_capability_scoped():
    workflow = load_json(WORKFLOW_PATH)
    engine = workflow["engine_spec"]
    module = load_json(MODULE_PATH)
    module_commands = {command["id"] for command in module["commands"]}
    expected_action_ids = {command_id.replace(".", "_") for command_id in module_commands}

    assert engine["id"] == "github-issue-to-pr"
    assert engine["version"] == workflow["version"]
    assert engine["capabilities"] == workflow["capabilities"]
    assert engine["capabilities"] == {
        "providers": ["github"],
        "max_spend_cents": 0,
        "allow_irreversible": True,
    }

    nodes = engine["nodes"]
    assert len(nodes) == len(workflow["nodes"])
    assert all(node["type"] == "effect" for node in nodes)
    assert all(node["provider"] == "github" for node in nodes)
    assert {node["action_id"] for node in nodes} <= expected_action_ids
    assert engine["edges"] == workflow["edges"][1:]
    assert workflow["module_dependency"]["minimum_version"] == "1.2.0"


def test_engine_spec_preserves_order_guards_and_bindings():
    workflow = load_json(WORKFLOW_PATH)
    nodes = {node["id"]: node for node in workflow["engine_spec"]["nodes"]}

    assert nodes["create_work_branch"]["parent"] == "inspect_issue"
    assert nodes["create_work_branch"]["args"]["expected_source_sha"] == "{{ctx.expected_source_sha}}"
    assert nodes["write_change"]["parent"] == "create_work_branch"
    assert nodes["open_pull_request"]["parent"] == "write_change"
    assert nodes["request_reviewers"]["cond"] == {"ctx": "reviewers_present", "eq": True}
    assert nodes["request_reviewers"]["args"]["pull_number"] == "{{nodes.open_pull_request.pull_request.number}}"
    assert nodes["verify_checks"]["args"]["ref"] == "{{nodes.write_change.commit_sha}}"


def test_workflow_storefront_links_are_present():
    workflow = load_json(WORKFLOW_PATH)

    assert workflow["homepage"].startswith("https://github.com/tinyopsstudio/")
    assert workflow["tests_url"].startswith("https://github.com/tinyopsstudio/")
    assert workflow["video_url"] == "https://youtu.be/8BdXElhlT5s"


def load_tests(loader, tests, pattern):
    """Expose the function-style workflow tests to unittest discovery and CI."""
    suite = unittest.TestSuite()
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            suite.addTest(unittest.FunctionTestCase(function, description=name))
    return suite
