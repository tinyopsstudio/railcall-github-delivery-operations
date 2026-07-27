#!/usr/bin/env python3
"""One-shot live integration cycle for a disposable private GitHub repository.

The caller creates ``railcall-live-smoke`` from ``main`` before running this
script. Writes require an explicit environment guard. The token is read only
from the environment and is never printed.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import time


MODULE_DIR = Path(__file__).resolve().parents[1]
HANDLER_PATH = MODULE_DIR / "handlers" / "handler.py"


def required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main():
    if os.environ.get("RAILCALL_GITHUB_LIVE_WRITES") != "I_UNDERSTAND":
        raise RuntimeError(
            "set RAILCALL_GITHUB_LIVE_WRITES=I_UNDERSTAND for the disposable write cycle"
        )

    vault = {
        "github": {
            "token": required_env("RAILCALL_GITHUB_TOKEN"),
            "owner": required_env("RAILCALL_GITHUB_OWNER"),
            "repo": required_env("RAILCALL_GITHUB_REPO"),
        }
    }

    spec = importlib.util.spec_from_file_location("github_delivery_live", HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    module.__dict__["__rc_helpers__"] = {
        "vault_get": lambda provider: vault.get(provider)
    }
    spec.loader.exec_module(module)

    branch = os.environ.get("RAILCALL_GITHUB_BRANCH", "railcall-live-smoke")
    base = os.environ.get("RAILCALL_GITHUB_BASE", "main")
    output = {}

    output["initial_pull_requests"], _ = module.github_list_pull_requests(
        {"state": "all", "per_page": 20},
        {},
    )

    output["fixture_file"], _ = module.github_put_file(
        {
            "path": "fixtures/railcall-module-smoke.txt",
            "message": "Add RailCall module integration fixture",
            "content": "GitHub Delivery Operations live API check.\n",
            "branch": branch,
        },
        {},
    )

    workflow = """name: RailCall Module Smoke

on:
  workflow_dispatch:
    inputs:
      environment:
        description: Integration fixture value
        required: true
        type: string

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Confirm dispatch input
        run: test "${{ inputs.environment }}" = "fixture"
"""
    output["workflow_file"], _ = module.github_put_file(
        {
            "path": ".github/workflows/railcall-smoke.yml",
            "message": "Add RailCall module smoke workflow",
            "content": workflow,
            "branch": branch,
        },
        {},
    )

    output["created_pull_request"], _ = module.github_create_pull_request(
        {
            "title": "RailCall GitHub module live smoke",
            "head": branch,
            "base": base,
            "body": (
                "Private integration fixture created through the signed "
                "RailCall GitHub Delivery Operations module."
            ),
        },
        {},
    )
    pull_number = output["created_pull_request"]["pull_request"]["number"]

    output["listed_pull_requests"], _ = module.github_list_pull_requests(
        {"state": "open", "head": branch, "base": base, "per_page": 20},
        {},
    )
    output["read_pull_request"], _ = module.github_get_pull_request(
        {"pull_number": pull_number},
        {},
    )
    head_sha = output["read_pull_request"]["pull_request"]["head_sha"]

    output["pull_request_comment"], _ = module.github_add_issue_comment(
        {
            "issue_number": pull_number,
            "body": "Live module check: pull-request comment write confirmed.",
        },
        {},
    )
    output["merged_pull_request"], _ = module.github_merge_pull_request(
        {
            "pull_number": pull_number,
            "merge_method": "squash",
            "expected_head_sha": head_sha,
        },
        {},
    )

    # Give GitHub time to index the newly merged workflow before the one and
    # only dispatch attempt. The module itself never retries writes.
    time.sleep(10)
    output["workflow_dispatch"], _ = module.github_dispatch_workflow(
        {
            "workflow_id": "railcall-smoke.yml",
            "ref": base,
            "inputs": {"environment": "fixture"},
        },
        {},
    )

    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
