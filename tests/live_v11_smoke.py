#!/usr/bin/env python3
"""Live v1.1 branch and CI read checks for a disposable GitHub repository."""

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
            "set RAILCALL_GITHUB_LIVE_WRITES=I_UNDERSTAND for the disposable branch cycle"
        )

    vault = {
        "github": {
            "token": required_env("RAILCALL_GITHUB_TOKEN"),
            "owner": required_env("RAILCALL_GITHUB_OWNER"),
            "repo": required_env("RAILCALL_GITHUB_REPO"),
        }
    }
    spec = importlib.util.spec_from_file_location("github_delivery_v11_live", HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    module.__dict__["__rc_helpers__"] = {
        "vault_get": lambda provider: vault.get(provider)
    }
    spec.loader.exec_module(module)

    source_branch = os.environ.get("RAILCALL_GITHUB_BASE", "main")
    branch = f"railcall-v11-smoke-{int(time.time())}"
    output = {}
    created = False

    branches, _ = module.github_list_branches({"per_page": 100}, {})
    output["initial_branches"] = branches
    source = next(
        (item for item in branches["branches"] if item.get("name") == source_branch),
        None,
    )
    if not source or not source.get("sha"):
        raise RuntimeError(f"source branch {source_branch} was not returned")

    try:
        output["created_branch"], _ = module.github_create_branch(
            {
                "branch": branch,
                "source_branch": source_branch,
                "expected_source_sha": source["sha"],
            },
            {},
        )
        created = True
        output["workflow_runs"], _ = module.github_list_workflow_runs(
            {"branch": source_branch, "per_page": 10},
            {},
        )
        runs = output["workflow_runs"]["workflow_runs"]
        if runs:
            output["workflow_run"], _ = module.github_get_workflow_run(
                {"run_id": runs[0]["id"]},
                {},
            )
        output["check_runs"], _ = module.github_list_check_runs(
            {"ref": source_branch, "filter": "latest", "per_page": 20},
            {},
        )
        try:
            output["branch_protection"], _ = module.github_get_branch_protection(
                {"branch": source_branch},
                {},
            )
        except RuntimeError as exc:
            if not any(code in str(exc) for code in ("GitHub HTTP 403", "GitHub HTTP 404")):
                raise
            output["branch_protection"] = {
                "ok": True,
                "configured": False,
                "note": (
                    "The disposable private repository has no branch-protection "
                    "entitlement or configured rule."
                ),
            }
    finally:
        if created:
            output["deleted_branch"], _ = module.github_delete_branch(
                {"branch": branch},
                {},
            )

    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
