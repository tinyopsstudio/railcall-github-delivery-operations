"""Governed GitHub delivery operations for RailCall.

The module complements RailCall's built-in issue listing and creation commands
with the actions needed to move work from an issue through a pull request and
deployment trigger.

Credentials are read only from RailCall's local ``github`` vault entry. Reads
use bounded retries. Writes are never retried automatically because a lost
response can leave the remote outcome uncertain.
"""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request


_HELPERS = globals().get("__rc_helpers__") or {}
_VAULT_GET = _HELPERS.get("vault_get")
_URLOPEN = urllib.request.urlopen
_SLEEP = time.sleep

_DEFAULT_API_URL = "https://api.github.com"
_REPO_PART_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_TOKEN_RE = re.compile(r"^\S{16,512}$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
_WORKFLOW_RE = re.compile(r"^[A-Za-z0-9._-]{1,255}$")
_TRANSIENT_READ_CODES = {429, 502, 503, 504}


def _text(value, field, *, required=True, maximum=65_536, strip=True):
    if value is None:
        if required:
            raise RuntimeError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise RuntimeError(f"{field} must be a string")
    clean = value.strip() if strip else value
    if required and not clean:
        raise RuntimeError(f"{field} must be a non-empty string")
    if len(clean) > maximum:
        raise RuntimeError(f"{field} exceeds the {maximum}-character limit")
    return clean


def _positive_int(value, field, *, maximum=2_147_483_647):
    if isinstance(value, bool):
        raise RuntimeError(f"{field} must be a positive integer")
    if isinstance(value, float) and not value.is_integer():
        raise RuntimeError(f"{field} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{field} must be a positive integer") from exc
    if number < 1 or number > maximum:
        raise RuntimeError(f"{field} must be between 1 and {maximum}")
    return number


def _boolean(value, field):
    if not isinstance(value, bool):
        raise RuntimeError(f"{field} must be a boolean")
    return value


def _enum(value, field, allowed, *, default=None):
    if value is None and default is not None:
        value = default
    clean = _text(value, field, maximum=64).lower()
    if clean not in allowed:
        choices = ", ".join(sorted(allowed))
        raise RuntimeError(f"{field} must be one of: {choices}")
    return clean


def _string_list(value, field, *, maximum_items=20):
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError(f"{field} must be an array of strings")
    if len(value) > maximum_items:
        raise RuntimeError(f"{field} cannot contain more than {maximum_items} values")
    result = []
    seen = set()
    for index, item in enumerate(value):
        clean = _text(item, f"{field}[{index}]", maximum=100)
        if clean not in seen:
            result.append(clean)
            seen.add(clean)
    return result


def _scalar_map(value, field, *, maximum_items=50):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RuntimeError(f"{field} must be an object")
    if len(value) > maximum_items:
        raise RuntimeError(f"{field} cannot contain more than {maximum_items} keys")
    result = {}
    for key, item in value.items():
        clean_key = _text(key, f"{field} key", maximum=100)
        if not isinstance(item, (str, int, float, bool)) or item is None:
            raise RuntimeError(f"{field}.{clean_key} must be a string, number, or boolean")
        if isinstance(item, str) and len(item) > 10_000:
            raise RuntimeError(f"{field}.{clean_key} exceeds the 10000-character limit")
        result[clean_key] = item
    return result


def _content_path(value):
    path = _text(value, "path", maximum=1_024)
    if path.startswith("/") or "\\" in path or "\x00" in path:
        raise RuntimeError("path must be a repository-relative POSIX path")
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise RuntimeError("path cannot contain empty, dot, or parent segments")
    return path


def _repo_part(value, field):
    clean = _text(value, field, maximum=100)
    if not _REPO_PART_RE.fullmatch(clean):
        raise RuntimeError(f"{field} contains unsupported characters")
    return clean


def _api_url(value):
    clean = _text(value or _DEFAULT_API_URL, "api_url", maximum=500)
    parsed = urllib.parse.urlsplit(clean)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("api_url must be an HTTPS origin or GitHub Enterprise API base")
    return clean.rstrip("/")


def _credentials():
    if not callable(_VAULT_GET):
        raise RuntimeError("RailCall vault helper is unavailable")
    entry = _VAULT_GET("github")
    if not isinstance(entry, dict):
        raise RuntimeError(
            "no GitHub credential saved - configure token, owner, and repo in the github vault entry"
        )
    token = str(entry.get("token") or entry.get("GITHUB_TOKEN") or "").strip()
    owner = str(entry.get("owner") or entry.get("GITHUB_OWNER") or "").strip()
    repo = str(entry.get("repo") or entry.get("GITHUB_REPO") or "").strip()
    api_url = entry.get("api_url") or entry.get("GITHUB_API_URL") or _DEFAULT_API_URL
    if not _TOKEN_RE.fullmatch(token):
        raise RuntimeError("GitHub credential token is missing or malformed")
    return token, _repo_part(owner, "owner"), _repo_part(repo, "repo"), _api_url(api_url)


def _headers(token):
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "User-Agent": "RailCall-GitHub-Delivery-Operations/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _error_detail(raw):
    try:
        parsed = json.loads(raw.decode("utf-8"))
        if isinstance(parsed, dict):
            detail = parsed.get("message")
            errors = parsed.get("errors")
            if errors:
                suffix = json.dumps(errors, separators=(",", ":"))[:300]
                detail = f"{detail}: {suffix}" if detail else suffix
            if detail:
                return str(detail)[:500]
    except Exception:
        pass
    return raw.decode("utf-8", errors="replace")[:500] or "empty response"


def _decode_json(raw):
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("GitHub returned a non-JSON response") from exc


def _retry_delay(headers, attempt):
    try:
        retry_after = float(headers.get("Retry-After") or 0)
    except Exception:
        retry_after = 0.0
    return min(2.0, max(retry_after, 0.25 * (2**attempt)))


def _request(method, path, *, payload=None, query=None, write=False, expected=(200,)):
    if not path.startswith("/") or ".." in urllib.parse.unquote(path):
        raise RuntimeError("invalid GitHub API path")
    token, owner, repo, api_url = _credentials()
    repo_prefix = (
        "/repos/"
        + urllib.parse.quote(owner, safe="")
        + "/"
        + urllib.parse.quote(repo, safe="")
    )
    url = api_url + repo_prefix + path
    if query:
        clean_query = {key: value for key, value in query.items() if value is not None}
        if clean_query:
            url += "?" + urllib.parse.urlencode(clean_query)
    data = None
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers=_headers(token),
    )

    attempts = 1 if write else 3
    for attempt in range(attempts):
        try:
            with _URLOPEN(request, timeout=25) as response:
                status = response.getcode()
                raw = response.read()
                if status not in expected:
                    raise RuntimeError(f"GitHub returned unexpected HTTP {status}")
                return status, _decode_json(raw)
        except urllib.error.HTTPError as exc:
            raw = b""
            try:
                raw = exc.read()[:2_048]
            except Exception:
                pass
            can_retry = (
                not write
                and attempt + 1 < attempts
                and (
                    exc.code in _TRANSIENT_READ_CODES
                    or (exc.code == 403 and exc.headers.get("Retry-After"))
                )
            )
            if can_retry:
                _SLEEP(_retry_delay(exc.headers, attempt))
                continue
            if write and exc.code >= 500:
                raise RuntimeError(
                    f"GitHub write returned HTTP {exc.code}; outcome is unknown and was not retried. "
                    "Inspect GitHub state before approving a fresh attempt."
                ) from exc
            if write and exc.code == 429:
                raise RuntimeError(
                    "GitHub rate limited this write; it was not retried automatically. "
                    "Approve a fresh attempt after the rate limit clears."
                ) from exc
            raise RuntimeError(f"GitHub HTTP {exc.code}: {_error_detail(raw)}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if write:
                raise RuntimeError(
                    "GitHub write transport failed; outcome is unknown and was not retried. "
                    "Inspect GitHub state before approving a fresh attempt."
                ) from exc
            if attempt + 1 < attempts:
                _SLEEP(0.25 * (2**attempt))
                continue
            reason = getattr(exc, "reason", str(exc))
            raise RuntimeError(f"GitHub network error after bounded retries: {reason}") from exc
    raise RuntimeError("GitHub request failed after bounded retries")


def _compact_user(user):
    return user.get("login") if isinstance(user, dict) else None


def _compact_issue(issue):
    labels = []
    for label in (issue.get("labels") or [])[:20]:
        if isinstance(label, dict):
            labels.append(label.get("name"))
        elif isinstance(label, str):
            labels.append(label)
    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "state_reason": issue.get("state_reason"),
        "html_url": issue.get("html_url"),
        "is_pull_request": isinstance(issue.get("pull_request"), dict),
        "author": _compact_user(issue.get("user")),
        "assignees": [
            login
            for login in (_compact_user(item) for item in (issue.get("assignees") or [])[:20])
            if login
        ],
        "labels": [label for label in labels if label],
        "comments": issue.get("comments"),
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
    }


def _compact_pull_request(pull):
    head = pull.get("head") if isinstance(pull.get("head"), dict) else {}
    base = pull.get("base") if isinstance(pull.get("base"), dict) else {}
    return {
        "number": pull.get("number"),
        "title": pull.get("title"),
        "state": pull.get("state"),
        "draft": bool(pull.get("draft")),
        "merged": bool(pull.get("merged")),
        "mergeable": pull.get("mergeable"),
        "html_url": pull.get("html_url"),
        "author": _compact_user(pull.get("user")),
        "head_ref": head.get("ref"),
        "head_sha": head.get("sha"),
        "base_ref": base.get("ref"),
        "created_at": pull.get("created_at"),
        "updated_at": pull.get("updated_at"),
    }


def _require_object(payload, label):
    if not isinstance(payload, dict):
        raise RuntimeError(f"GitHub returned an unexpected {label} payload")
    return payload


def github_get_issue(inputs, stamp):
    issue_number = _positive_int(inputs.get("issue_number"), "issue_number")
    status, payload = _request("GET", f"/issues/{issue_number}", expected=(200,))
    issue = _require_object(payload, "issue")
    return {
        "ok": True,
        "http_status": status,
        "issue": _compact_issue(issue),
    }, None


def github_update_issue(inputs, stamp):
    issue_number = _positive_int(inputs.get("issue_number"), "issue_number")
    changes = {}
    if "title" in inputs:
        changes["title"] = _text(inputs.get("title"), "title", maximum=256)
    if "body" in inputs:
        changes["body"] = _text(
            inputs.get("body"),
            "body",
            required=False,
            maximum=65_536,
            strip=False,
        )
    if "state" in inputs:
        changes["state"] = _enum(inputs.get("state"), "state", {"open", "closed"})
    if not changes:
        raise RuntimeError("provide at least one of title, body, or state")
    status, payload = _request(
        "PATCH",
        f"/issues/{issue_number}",
        payload=changes,
        write=True,
        expected=(200,),
    )
    issue = _require_object(payload, "updated issue")
    return {
        "ok": True,
        "http_status": status,
        "issue": _compact_issue(issue),
    }, None


def github_add_issue_comment(inputs, stamp):
    issue_number = _positive_int(inputs.get("issue_number"), "issue_number")
    body = _text(inputs.get("body"), "body", maximum=65_536, strip=False)
    status, payload = _request(
        "POST",
        f"/issues/{issue_number}/comments",
        payload={"body": body},
        write=True,
        expected=(201,),
    )
    comment = _require_object(payload, "comment")
    if not comment.get("id"):
        raise RuntimeError("GitHub accepted the comment but returned no comment identifier")
    return {
        "ok": True,
        "http_status": status,
        "comment_id": comment.get("id"),
        "html_url": comment.get("html_url"),
        "created_at": comment.get("created_at"),
    }, None


def github_list_pull_requests(inputs, stamp):
    state = _enum(inputs.get("state"), "state", {"open", "closed", "all"}, default="open")
    sort = _enum(
        inputs.get("sort"),
        "sort",
        {"created", "updated", "popularity", "long-running"},
        default="updated",
    )
    direction = _enum(
        inputs.get("direction"),
        "direction",
        {"asc", "desc"},
        default="desc",
    )
    per_page = _positive_int(inputs.get("per_page") or 30, "per_page", maximum=100)
    head = _text(inputs.get("head"), "head", required=False, maximum=256)
    base = _text(inputs.get("base"), "base", required=False, maximum=256)
    status, payload = _request(
        "GET",
        "/pulls",
        query={
            "state": state,
            "sort": sort,
            "direction": direction,
            "per_page": per_page,
            "head": head,
            "base": base,
        },
        expected=(200,),
    )
    if not isinstance(payload, list):
        raise RuntimeError("GitHub returned an unexpected pull request list")
    pulls = [_compact_pull_request(item) for item in payload[:per_page] if isinstance(item, dict)]
    return {
        "ok": True,
        "http_status": status,
        "count": len(pulls),
        "pull_requests": pulls,
    }, None


def github_get_pull_request(inputs, stamp):
    pull_number = _positive_int(inputs.get("pull_number"), "pull_number")
    status, payload = _request("GET", f"/pulls/{pull_number}", expected=(200,))
    pull = _require_object(payload, "pull request")
    return {
        "ok": True,
        "http_status": status,
        "pull_request": _compact_pull_request(pull),
    }, None


def github_create_pull_request(inputs, stamp):
    title = _text(inputs.get("title"), "title", maximum=256)
    head = _text(inputs.get("head"), "head", maximum=256)
    base = _text(inputs.get("base"), "base", maximum=256)
    body = _text(
        inputs.get("body"),
        "body",
        required=False,
        maximum=65_536,
        strip=False,
    )
    request_body = {"title": title, "head": head, "base": base}
    if body is not None:
        request_body["body"] = body
    if "draft" in inputs:
        request_body["draft"] = _boolean(inputs.get("draft"), "draft")
    status, payload = _request(
        "POST",
        "/pulls",
        payload=request_body,
        write=True,
        expected=(201,),
    )
    pull = _require_object(payload, "created pull request")
    if not pull.get("number"):
        raise RuntimeError("GitHub accepted the pull request but returned no number")
    return {
        "ok": True,
        "http_status": status,
        "pull_request": _compact_pull_request(pull),
    }, None


def github_request_pull_request_reviewers(inputs, stamp):
    pull_number = _positive_int(inputs.get("pull_number"), "pull_number")
    reviewers = _string_list(inputs.get("reviewers"), "reviewers")
    team_reviewers = _string_list(inputs.get("team_reviewers"), "team_reviewers")
    if not reviewers and not team_reviewers:
        raise RuntimeError("provide at least one reviewer or team reviewer")
    status, payload = _request(
        "POST",
        f"/pulls/{pull_number}/requested_reviewers",
        payload={"reviewers": reviewers, "team_reviewers": team_reviewers},
        write=True,
        expected=(201,),
    )
    pull = _require_object(payload, "review request")
    requested_users = [
        login
        for login in (
            _compact_user(item) for item in (pull.get("requested_reviewers") or [])[:20]
        )
        if login
    ]
    requested_teams = [
        str(item.get("slug"))
        for item in (pull.get("requested_teams") or [])[:20]
        if isinstance(item, dict) and item.get("slug")
    ]
    return {
        "ok": True,
        "http_status": status,
        "pull_number": pull_number,
        "requested_reviewers": requested_users,
        "requested_teams": requested_teams,
    }, None


def github_merge_pull_request(inputs, stamp):
    pull_number = _positive_int(inputs.get("pull_number"), "pull_number")
    merge_method = _enum(
        inputs.get("merge_method"),
        "merge_method",
        {"merge", "squash", "rebase"},
        default="squash",
    )
    request_body = {"merge_method": merge_method}
    commit_title = _text(
        inputs.get("commit_title"),
        "commit_title",
        required=False,
        maximum=256,
    )
    commit_message = _text(
        inputs.get("commit_message"),
        "commit_message",
        required=False,
        maximum=65_536,
        strip=False,
    )
    expected_head_sha = _text(
        inputs.get("expected_head_sha"),
        "expected_head_sha",
        required=False,
        maximum=64,
    )
    if expected_head_sha and not _SHA_RE.fullmatch(expected_head_sha):
        raise RuntimeError("expected_head_sha must be a 40-64 character hexadecimal commit SHA")
    if commit_title is not None:
        request_body["commit_title"] = commit_title
    if commit_message is not None:
        request_body["commit_message"] = commit_message
    if expected_head_sha is not None:
        request_body["sha"] = expected_head_sha
    status, payload = _request(
        "PUT",
        f"/pulls/{pull_number}/merge",
        payload=request_body,
        write=True,
        expected=(200,),
    )
    result = _require_object(payload, "merge")
    if not isinstance(result.get("merged"), bool):
        raise RuntimeError("GitHub returned an unexpected merge result")
    return {
        "ok": bool(result.get("merged")),
        "http_status": status,
        "pull_number": pull_number,
        "merged": result.get("merged"),
        "message": result.get("message"),
        "sha": result.get("sha"),
    }, None


def github_dispatch_workflow(inputs, stamp):
    workflow_id = _text(inputs.get("workflow_id"), "workflow_id", maximum=255)
    if not _WORKFLOW_RE.fullmatch(workflow_id):
        raise RuntimeError("workflow_id must be a numeric ID or workflow file name")
    ref = _text(inputs.get("ref"), "ref", maximum=256)
    workflow_inputs = _scalar_map(inputs.get("inputs"), "inputs")
    request_body = {"ref": ref}
    if workflow_inputs:
        request_body["inputs"] = workflow_inputs
    encoded_workflow = urllib.parse.quote(workflow_id, safe="")
    status, _payload = _request(
        "POST",
        f"/actions/workflows/{encoded_workflow}/dispatches",
        payload=request_body,
        write=True,
        expected=(204,),
    )
    return {
        "ok": True,
        "http_status": status,
        "workflow_id": workflow_id,
        "ref": ref,
    }, None


def github_put_file(inputs, stamp):
    path = _content_path(inputs.get("path"))
    message = _text(inputs.get("message"), "message", maximum=256)
    content = _text(
        inputs.get("content"),
        "content",
        maximum=1_000_000,
        strip=False,
    )
    branch = _text(inputs.get("branch"), "branch", required=False, maximum=256)
    expected_sha = _text(
        inputs.get("expected_sha"),
        "expected_sha",
        required=False,
        maximum=64,
    )
    if expected_sha and not _SHA_RE.fullmatch(expected_sha):
        raise RuntimeError("expected_sha must be a 40-64 character hexadecimal blob SHA")
    request_body = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
    }
    if branch is not None:
        request_body["branch"] = branch
    if expected_sha is not None:
        request_body["sha"] = expected_sha
    encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
    status, payload = _request(
        "PUT",
        f"/contents/{encoded_path}",
        payload=request_body,
        write=True,
        expected=(200, 201),
    )
    result = _require_object(payload, "repository content")
    content_result = result.get("content") if isinstance(result.get("content"), dict) else {}
    commit = result.get("commit") if isinstance(result.get("commit"), dict) else {}
    if not commit.get("sha"):
        raise RuntimeError("GitHub accepted the file write but returned no commit SHA")
    return {
        "ok": True,
        "http_status": status,
        "path": content_result.get("path") or path,
        "content_sha": content_result.get("sha"),
        "content_url": content_result.get("html_url"),
        "commit_sha": commit.get("sha"),
        "commit_url": commit.get("html_url"),
    }, None
