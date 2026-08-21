from __future__ import annotations

import base64
import importlib.util
import io
import json
from pathlib import Path
import unittest
import urllib.error


MODULE_DIR = Path(__file__).resolve().parents[1]
HANDLER_PATH = MODULE_DIR / "handlers" / "handler.py"
MANIFEST_PATH = MODULE_DIR / "module.json"

VAULT = {}


def _vault_get(provider):
    return VAULT.get(provider)


spec = importlib.util.spec_from_file_location("github_delivery_handler", HANDLER_PATH)
handler = importlib.util.module_from_spec(spec)
handler.__dict__["__rc_helpers__"] = {"vault_get": _vault_get}
spec.loader.exec_module(handler)


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status = status
        if payload is None:
            self.raw = b""
        elif isinstance(payload, bytes):
            self.raw = payload
        else:
            self.raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def getcode(self):
        return self.status

    def read(self):
        return self.raw


def http_error(code, payload, headers=None):
    raw = json.dumps(payload).encode("utf-8")
    return urllib.error.HTTPError(
        "https://api.github.com/test",
        code,
        "error",
        headers or {},
        io.BytesIO(raw),
    )


class GitHubDeliveryHandlerTests(unittest.TestCase):
    def setUp(self):
        VAULT.clear()
        VAULT["github"] = {
            "token": "g" * 40,
            "owner": "tinyopsstudio",
            "repo": "module-test",
        }
        self.calls = []
        handler._SLEEP = lambda _seconds: None

    def route(self, *items):
        remaining = list(items)

        def fake_urlopen(request, timeout=0):
            self.calls.append((request, timeout))
            if not remaining:
                raise AssertionError("unexpected HTTP request")
            item = remaining.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item

        handler._URLOPEN = fake_urlopen

    def request_json(self, index=0):
        request = self.calls[index][0]
        return json.loads((request.data or b"{}").decode("utf-8"))

    def test_manifest_exposes_eighteen_matching_commands_and_store_metadata(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        commands = manifest["commands"]
        self.assertEqual("1.2.0", manifest["version"])
        self.assertEqual(18, len(commands))
        self.assertEqual(18, len({item["id"] for item in commands}))
        self.assertEqual("github", manifest["auth"]["vault_provider"])
        self.assertEqual("token", manifest["auth"]["secret_field"])
        self.assertTrue(manifest["auth"]["docs"].startswith("https://"))
        self.assertTrue(manifest["homepage"].startswith("https://"))
        self.assertTrue(manifest["tests_url"].startswith("https://"))
        self.assertEqual("https://youtu.be/8BdXElhlT5s", manifest["video_url"])
        self.assertEqual("Developer Tools", manifest["category"])
        self.assertEqual("github", manifest["credential_spec"]["provider"])
        self.assertEqual(["token", "owner", "repo"], manifest["credential_spec"]["required"])
        self.assertEqual(["api_url"], manifest["credential_spec"]["optional"])
        self.assertEqual("write", manifest["credential_spec"]["read_write"])
        self.assertGreaterEqual(len(manifest["description"]), 1_500)
        self.assertLessEqual(len(manifest["description"]), 2_500)
        for command in commands:
            function_name = command["id"].replace(".", "_").replace("-", "_")
            self.assertTrue(callable(getattr(handler, function_name, None)))
            self.assertTrue(command["preview"])
            self.assertTrue(command["receipt_required"])
            self.assertEqual(["github"], command["requires"])
            if command["mode"] != "read":
                self.assertEqual("write_requires_approval", command["mode"])

    def test_get_issue_uses_vault_header_and_compacts_response(self):
        self.route(
            FakeResponse(
                200,
                {
                    "number": 7,
                    "title": "Ship module",
                    "state": "open",
                    "html_url": "https://github.com/tinyopsstudio/module-test/issues/7",
                    "user": {"login": "tinyopsstudio"},
                    "assignees": [{"login": "reviewer"}],
                    "labels": [{"name": "delivery"}],
                    "comments": 2,
                    "created_at": "2026-07-26T00:00:00Z",
                    "updated_at": "2026-07-26T01:00:00Z",
                },
            )
        )

        result, artifact = handler.github_get_issue({"issue_number": 7}, {})

        self.assertIsNone(artifact)
        self.assertTrue(result["ok"])
        self.assertEqual("Ship module", result["issue"]["title"])
        self.assertEqual(["delivery"], result["issue"]["labels"])
        request = self.calls[0][0]
        self.assertEqual("GET", request.method)
        self.assertTrue(request.full_url.endswith("/repos/tinyopsstudio/module-test/issues/7"))
        self.assertNotIn("g" * 40, request.full_url)
        self.assertEqual("Bearer " + ("g" * 40), request.get_header("Authorization"))

    def test_read_retries_rate_limit_but_stops_after_success(self):
        self.route(
            http_error(429, {"message": "secondary rate limit"}, {"Retry-After": "0"}),
            FakeResponse(
                200,
                [
                    {
                        "number": 4,
                        "title": "Module release",
                        "state": "open",
                        "head": {"ref": "module", "sha": "a" * 40},
                        "base": {"ref": "main"},
                    }
                ],
            ),
        )

        result, _artifact = handler.github_list_pull_requests(
            {"state": "open", "per_page": 10},
            {},
        )

        self.assertEqual(2, len(self.calls))
        self.assertEqual(1, result["count"])
        self.assertIn("per_page=10", self.calls[-1][0].full_url)

    def test_write_transport_failure_is_not_retried(self):
        self.route(urllib.error.URLError("timed out"))

        with self.assertRaisesRegex(RuntimeError, "outcome is unknown"):
            handler.github_add_issue_comment(
                {"issue_number": 3, "body": "Status update"},
                {},
            )

        self.assertEqual(1, len(self.calls))

    def test_write_server_error_is_reported_as_ambiguous(self):
        self.route(http_error(503, {"message": "upstream unavailable"}))

        with self.assertRaisesRegex(RuntimeError, "outcome is unknown"):
            handler.github_update_issue(
                {"issue_number": 3, "state": "closed"},
                {},
            )

        self.assertEqual(1, len(self.calls))

    def test_update_issue_requires_a_real_change(self):
        with self.assertRaisesRegex(RuntimeError, "at least one"):
            handler.github_update_issue({"issue_number": 3}, {})
        self.assertEqual([], self.calls)

    def test_create_pull_request_shapes_approved_write(self):
        self.route(
            FakeResponse(
                201,
                {
                    "number": 11,
                    "title": "Add GitHub module",
                    "state": "open",
                    "draft": True,
                    "html_url": "https://github.com/tinyopsstudio/module-test/pull/11",
                    "head": {"ref": "railcall-module", "sha": "b" * 40},
                    "base": {"ref": "main"},
                },
            )
        )

        result, _artifact = handler.github_create_pull_request(
            {
                "title": "Add GitHub module",
                "head": "railcall-module",
                "base": "main",
                "body": "Reviewed delivery module.",
                "draft": True,
            },
            {},
        )

        self.assertEqual("POST", self.calls[0][0].method)
        self.assertEqual(
            {
                "title": "Add GitHub module",
                "head": "railcall-module",
                "base": "main",
                "body": "Reviewed delivery module.",
                "draft": True,
            },
            self.request_json(),
        )
        self.assertEqual(11, result["pull_request"]["number"])

    def test_review_request_rejects_empty_audience(self):
        with self.assertRaisesRegex(RuntimeError, "at least one reviewer"):
            handler.github_request_pull_request_reviewers(
                {"pull_number": 11, "reviewers": [], "team_reviewers": []},
                {},
            )

    def test_merge_uses_expected_head_sha(self):
        expected_sha = "c" * 40
        self.route(
            FakeResponse(
                200,
                {"sha": "d" * 40, "merged": True, "message": "Pull Request successfully merged"},
            )
        )

        result, _artifact = handler.github_merge_pull_request(
            {
                "pull_number": 11,
                "merge_method": "squash",
                "expected_head_sha": expected_sha,
            },
            {},
        )

        self.assertEqual("PUT", self.calls[0][0].method)
        self.assertEqual(
            {"merge_method": "squash", "sha": expected_sha},
            self.request_json(),
        )
        self.assertTrue(result["merged"])

    def test_dispatch_workflow_accepts_scalar_inputs_and_empty_response(self):
        self.route(FakeResponse(204))

        result, _artifact = handler.github_dispatch_workflow(
            {
                "workflow_id": "release.yml",
                "ref": "main",
                "inputs": {"environment": "staging", "dry_run": True},
            },
            {},
        )

        request = self.calls[0][0]
        self.assertEqual("POST", request.method)
        self.assertIn("/actions/workflows/release.yml/dispatches", request.full_url)
        self.assertEqual(
            {
                "ref": "main",
                "inputs": {"environment": "staging", "dry_run": True},
            },
            self.request_json(),
        )
        self.assertEqual(204, result["http_status"])

    def test_put_file_base64_encodes_utf8_and_returns_commit(self):
        self.route(
            FakeResponse(
                201,
                {
                    "content": {
                        "path": "docs/release.txt",
                        "sha": "e" * 40,
                        "html_url": "https://github.com/example/content",
                    },
                    "commit": {
                        "sha": "f" * 40,
                        "html_url": "https://github.com/example/commit",
                    },
                },
            )
        )

        result, _artifact = handler.github_put_file(
            {
                "path": "docs/release.txt",
                "message": "Add release note",
                "content": "ready\n",
                "branch": "module",
            },
            {},
        )

        request_body = self.request_json()
        self.assertEqual(
            b"ready\n",
            base64.b64decode(request_body["content"].encode("ascii")),
        )
        self.assertEqual("module", request_body["branch"])
        self.assertEqual("f" * 40, result["commit_sha"])

    def test_put_file_rejects_parent_traversal(self):
        with self.assertRaisesRegex(RuntimeError, "parent"):
            handler.github_put_file(
                {
                    "path": "../secret.txt",
                    "message": "Invalid",
                    "content": "no",
                },
                {},
            )

    def test_list_branches_filters_and_compacts_results(self):
        self.route(
            FakeResponse(
                200,
                [
                    {
                        "name": "main",
                        "commit": {"sha": "1" * 40},
                        "protected": True,
                        "protection_url": "https://api.github.com/protection",
                    }
                ],
            )
        )

        result, _artifact = handler.github_list_branches(
            {"protected": True, "per_page": 20},
            {},
        )

        request = self.calls[0][0]
        self.assertEqual("GET", request.method)
        self.assertIn("protected=true", request.full_url)
        self.assertIn("per_page=20", request.full_url)
        self.assertEqual(1, result["count"])
        self.assertEqual("1" * 40, result["branches"][0]["sha"])

    def test_create_branch_verifies_source_sha_before_single_write(self):
        source_sha = "2" * 40
        self.route(
            FakeResponse(
                200,
                {
                    "ref": "refs/heads/main",
                    "object": {"type": "commit", "sha": source_sha},
                },
            ),
            FakeResponse(
                201,
                {
                    "ref": "refs/heads/release/v1.1",
                    "url": "https://api.github.com/ref",
                    "object": {"type": "commit", "sha": source_sha},
                },
            ),
        )

        result, _artifact = handler.github_create_branch(
            {
                "branch": "release/v1.1",
                "source_branch": "main",
                "expected_source_sha": source_sha,
            },
            {},
        )

        self.assertEqual(2, len(self.calls))
        self.assertEqual("GET", self.calls[0][0].method)
        self.assertTrue(self.calls[0][0].full_url.endswith("/git/ref/heads/main"))
        self.assertEqual("POST", self.calls[1][0].method)
        self.assertEqual(
            {"ref": "refs/heads/release/v1.1", "sha": source_sha},
            self.request_json(1),
        )
        self.assertEqual(source_sha, result["sha"])

    def test_create_branch_stops_if_source_moved(self):
        self.route(
            FakeResponse(
                200,
                {
                    "ref": "refs/heads/main",
                    "object": {"type": "commit", "sha": "3" * 40},
                },
            )
        )

        with self.assertRaisesRegex(RuntimeError, "source branch moved"):
            handler.github_create_branch(
                {
                    "branch": "release/v1.1",
                    "source_branch": "main",
                    "expected_source_sha": "4" * 40,
                },
                {},
            )

        self.assertEqual(1, len(self.calls))

    def test_delete_branch_encodes_slash_and_does_not_retry(self):
        self.route(FakeResponse(204))

        result, _artifact = handler.github_delete_branch(
            {"branch": "release/v1.0"},
            {},
        )

        request = self.calls[0][0]
        self.assertEqual("DELETE", request.method)
        self.assertTrue(request.full_url.endswith("/git/refs/heads/release%2Fv1.0"))
        self.assertTrue(result["deleted"])
        self.assertEqual(1, len(self.calls))

    def test_get_branch_protection_compacts_sensitive_lists_to_counts(self):
        self.route(
            FakeResponse(
                200,
                {
                    "required_status_checks": {
                        "strict": True,
                        "contexts": ["tests", "lint"],
                    },
                    "enforce_admins": {"enabled": True},
                    "required_pull_request_reviews": {
                        "required_approving_review_count": 2,
                        "dismiss_stale_reviews": True,
                        "require_code_owner_reviews": True,
                    },
                    "allow_force_pushes": {"enabled": False},
                    "allow_deletions": {"enabled": False},
                    "restrictions": {
                        "users": [{"login": "maintainer"}],
                        "teams": [{"slug": "release"}],
                        "apps": [],
                    },
                },
            )
        )

        result, _artifact = handler.github_get_branch_protection(
            {"branch": "main"},
            {},
        )

        protection = result["protection"]
        self.assertEqual(["tests", "lint"], protection["required_status_checks"]["contexts"])
        self.assertEqual(2, protection["required_approving_review_count"])
        self.assertEqual(1, protection["restricted_users"])
        self.assertEqual(1, protection["restricted_teams"])

    def test_list_and_get_workflow_runs_compact_results(self):
        run_id = 12_345_678_901
        workflow_run = {
            "id": run_id,
            "name": "CI",
            "workflow_id": 9,
            "run_number": 44,
            "event": "push",
            "status": "completed",
            "conclusion": "failure",
            "head_branch": "main",
            "head_sha": "5" * 40,
            "head_commit": {"message": "Test v1.1"},
            "html_url": f"https://github.com/example/actions/runs/{run_id}",
        }
        self.route(
            FakeResponse(200, {"total_count": 1, "workflow_runs": [workflow_run]}),
            FakeResponse(200, workflow_run),
        )

        listed, _artifact = handler.github_list_workflow_runs(
            {"branch": "main", "status": "failure", "per_page": 10},
            {},
        )
        fetched, _artifact = handler.github_get_workflow_run({"run_id": run_id}, {})

        self.assertEqual(1, listed["count"])
        self.assertEqual("failure", listed["workflow_runs"][0]["conclusion"])
        self.assertIn("branch=main", self.calls[0][0].full_url)
        self.assertEqual(run_id, fetched["workflow_run"]["id"])
        self.assertTrue(self.calls[1][0].full_url.endswith(f"/actions/runs/{run_id}"))

    def test_cancel_workflow_run_is_a_single_attempt_write(self):
        self.route(FakeResponse(202))
        run_id = 12_345_678_901

        result, _artifact = handler.github_cancel_workflow_run({"run_id": run_id}, {})

        request = self.calls[0][0]
        self.assertEqual("POST", request.method)
        self.assertTrue(request.full_url.endswith(f"/actions/runs/{run_id}/cancel"))
        self.assertTrue(result["cancel_requested"])
        self.assertEqual(1, len(self.calls))

    def test_list_check_runs_accepts_branch_ref_and_compacts_results(self):
        self.route(
            FakeResponse(
                200,
                {
                    "total_count": 1,
                    "check_runs": [
                        {
                            "id": 91,
                            "name": "tests",
                            "status": "completed",
                            "conclusion": "success",
                            "head_sha": "6" * 40,
                            "html_url": "https://github.com/example/checks/91",
                            "app": {"slug": "github-actions"},
                        }
                    ],
                },
            )
        )

        result, _artifact = handler.github_list_check_runs(
            {"ref": "release/v1.1", "filter": "latest", "per_page": 20},
            {},
        )

        request = self.calls[0][0]
        self.assertIn("/commits/release%2Fv1.1/check-runs", request.full_url)
        self.assertEqual(1, result["count"])
        self.assertEqual("github-actions", result["check_runs"][0]["app"])

    def test_enterprise_api_base_is_vault_only(self):
        VAULT["github"]["api_url"] = "https://github.example.test/api/v3"
        self.route(FakeResponse(200, {"number": 2, "title": "Enterprise", "state": "open"}))

        handler.github_get_issue({"issue_number": 2}, {})

        self.assertTrue(
            self.calls[0][0].full_url.startswith(
                "https://github.example.test/api/v3/repos/"
            )
        )

    def test_token_never_appears_in_an_error(self):
        token = VAULT["github"]["token"]
        self.route(http_error(422, {"message": "Validation Failed"}))

        with self.assertRaises(RuntimeError) as raised:
            handler.github_create_pull_request(
                {"title": "Bad", "head": "missing", "base": "main"},
                {},
            )

        self.assertNotIn(token, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
