# GitHub Delivery Operations for RailCall

[![Tests](https://github.com/tinyopsstudio/railcall-github-delivery-operations/actions/workflows/test.yml/badge.svg)](https://github.com/tinyopsstudio/railcall-github-delivery-operations/actions/workflows/test.yml)
[![RailCall Marketplace](https://img.shields.io/badge/RailCall-Marketplace-0f766e)](https://railcall.ai/marketplace/tinyops-studio-llc/github-delivery-operations)

This module fills the gap between opening a GitHub issue and shipping the
change. It adds eighteen governed operations for issue updates, branches,
pull requests, merges, Actions dispatches and run observability, checks, and
repository file writes.

The module is free. It supports GitHub.com and HTTPS GitHub Enterprise API
bases.

Install it from the
[RailCall Marketplace](https://railcall.ai/marketplace/tinyops-studio-llc/github-delivery-operations).

Watch the
[race-safe branch creation walkthrough](https://youtu.be/8BdXElhlT5s)
for the stale-source failure path, single-write approval boundary, focused
regression tests, and live GitHub smoke evidence.

## Self-serve operations pack

TinyOps offers a $49 operations pack for teams that can install the module but
want a concrete permission matrix, approval worksheet, eighteen-command
smoke-test plan, operator runbook, rollback procedure, and editable evidence
records.

The download contains 13 files and is designed for one GitHub.com or HTTPS
GitHub Enterprise repository. The signed runtime module remains free.

[Get the RailCall GitHub Operations Pack](https://tinyopsstudio.gumroad.com/l/railcall-github-operations-pack?utm_source=github&utm_medium=repository&utm_campaign=railcall_operations_pack_launch&utm_content=readme)

## Managed setup

TinyOps offers a fixed-scope $499 setup for one repository when a team wants
the module configured and verified rather than installing it alone. The
delivery includes a repository permission map, approval matrix, bounded command
configuration, smoke-test results, and an operator runbook.

Your GitHub credentials remain in your own RailCall vault. Review the exact
scope and send non-secret workflow details on the
[managed setup page](https://tinyopsstudio.com/railcall-github-delivery-operations-setup).

## Commands

| Command | Effect |
| --- | --- |
| `github.get_issue` | Read one issue or pull-request issue record |
| `github.update_issue` | Change an issue title, body, or state |
| `github.add_issue_comment` | Add a comment to an issue or pull request |
| `github.list_pull_requests` | List pull requests with bounded filters |
| `github.get_pull_request` | Read a pull request and its current head SHA |
| `github.create_pull_request` | Open a pull request |
| `github.request_pull_request_reviewers` | Request user or team reviewers |
| `github.merge_pull_request` | Merge, squash, or rebase a pull request |
| `github.dispatch_workflow` | Trigger a `workflow_dispatch` workflow |
| `github.put_file` | Create or update one UTF-8 repository file |
| `github.list_branches` | List branches and compact protection status |
| `github.create_branch` | Create a branch after verifying its source SHA |
| `github.delete_branch` | Delete one branch through the approval airlock |
| `github.get_branch_protection` | Read compact branch protection settings |
| `github.list_workflow_runs` | List Actions runs with bounded filters |
| `github.get_workflow_run` | Read one Actions run |
| `github.cancel_workflow_run` | Request cancellation of one Actions run |
| `github.list_check_runs` | List checks for a commit, branch, or tag |

RailCall already includes `github.list_issues` and `github.create_issue`.
Together, the built-ins and this module cover a practical issue-to-delivery
workflow without replacing GitHub's own review controls.

## Install

```bash
railcall market install tinyops-studio-llc/github-delivery-operations
```

Restart Studio or reload modules after installation.

The published `module.json`, `module.sig`, and `handlers/handler.py` are the
exact signed runtime bundle for marketplace version `1.1.0`. The tests and
documentation are published for independent review.

## Configure

Store credentials in RailCall's local `github` vault entry. Secrets never
belong in command inputs.

```json
{
  "github": {
    "token": "YOUR_TOKEN",
    "owner": "your-org",
    "repo": "your-repo"
  }
}
```

Uppercase names also work:

```json
{
  "github": {
    "GITHUB_TOKEN": "YOUR_TOKEN",
    "GITHUB_OWNER": "your-org",
    "GITHUB_REPO": "your-repo"
  }
}
```

For GitHub Enterprise Server, add its HTTPS API base:

```json
{
  "github": {
    "token": "YOUR_TOKEN",
    "owner": "your-org",
    "repo": "your-repo",
    "api_url": "https://github.example.com/api/v3"
  }
}
```

Use a fine-grained token or GitHub App installation token with only the
repository permissions required by the commands you plan to run:

- Metadata: read
- Issues: read and write
- Pull requests: read and write
- Actions: read and write
- Contents: read and write
- Checks: read

GitHub administrators can narrow those permissions further when only a subset
of commands is needed.

## Command examples

Each entry below is one RailCall command and its `inputs` object:

```json
[
  {"command":"github.get_issue","inputs":{"issue_number":42}},
  {"command":"github.update_issue","inputs":{"issue_number":42,"state":"closed"}},
  {"command":"github.add_issue_comment","inputs":{"issue_number":42,"body":"Deployed to staging."}},
  {"command":"github.list_pull_requests","inputs":{"state":"open","per_page":10}},
  {"command":"github.get_pull_request","inputs":{"pull_number":17}},
  {"command":"github.create_pull_request","inputs":{"title":"Ship v1.1","head":"release/v1.1","base":"main","draft":true}},
  {"command":"github.request_pull_request_reviewers","inputs":{"pull_number":17,"reviewers":["octocat"]}},
  {"command":"github.merge_pull_request","inputs":{"pull_number":17,"merge_method":"squash","expected_head_sha":"0123456789abcdef0123456789abcdef01234567"}},
  {"command":"github.dispatch_workflow","inputs":{"workflow_id":"deploy.yml","ref":"main","inputs":{"environment":"staging"}}},
  {"command":"github.put_file","inputs":{"path":"docs/release.md","message":"Add release notes","content":"Ready\n","branch":"release/v1.1"}},
  {"command":"github.list_branches","inputs":{"protected":true,"per_page":20}},
  {"command":"github.create_branch","inputs":{"branch":"release/v1.1","source_branch":"main","expected_source_sha":"0123456789abcdef0123456789abcdef01234567"}},
  {"command":"github.delete_branch","inputs":{"branch":"release/v1.0"}},
  {"command":"github.get_branch_protection","inputs":{"branch":"main"}},
  {"command":"github.list_workflow_runs","inputs":{"branch":"main","status":"failure","per_page":10}},
  {"command":"github.get_workflow_run","inputs":{"run_id":123456}},
  {"command":"github.cancel_workflow_run","inputs":{"run_id":123456}},
  {"command":"github.list_check_runs","inputs":{"ref":"main","filter":"latest","per_page":20}}
]
```

## Ten-minute check

Use a disposable private repository for the first run.

```bash
railcall run github.get_issue --issue_number=1
railcall run github.list_pull_requests --state=open --per_page=10
```

Then stage one reversible write and inspect RailCall's preview before approval:

```bash
railcall run github.add_issue_comment \
  --issue_number=1 \
  --body="RailCall module installation check."
```

For a merge, read the pull request first and pass its returned `head_sha` as
`expected_head_sha`. GitHub refuses the merge if the branch moved between the
read and the approved write.

## Failure behavior

- Reads retry a maximum of three times for transport failures and selected
  transient GitHub responses.
- Writes are never retried automatically.
- A write that loses transport confirmation or receives a server-side 5xx
  reports that the outcome is unknown. Inspect GitHub before approving another
  attempt.
- Inputs are bounded. Repository paths reject parent traversal, workflow IDs
  are constrained, and responses are compacted before they enter receipts.
- The token is sent only in the `Authorization` header. It never appears in a
  command input, result object, or module log.

## Verification

The v1.1 release was validated through three layers:

- 25 unit and bundle tests, including exact Ed25519 signature verification
- A live disposable-repository cycle created and deleted a branch, fetched a
  real 64-bit Actions run, and read its latest check run
- The CI workflow reruns the public test suite on Python 3.11, 3.12, and 3.13

Live tests are intentionally excluded from public CI because they require a
private GitHub token and a disposable repository.

## Local development

Run the tests:

```bash
python3 -m unittest discover -s tests -v
```

Sign the exact manifest and handler bytes with the publisher key:

```bash
python3 tools/sign_module.py .
```

Install the local bundle into an isolated RailCall workspace and verify that
all eighteen commands load before publishing.

## Scope

This module deliberately omits administrator, billing, secret-management, and
repository deletion actions. Those are not necessary for the issue-to-delivery
workflow and would enlarge the trust surface without improving the core use
case.

Built by TinyOps Studio LLC for the RailCall 2026 Q3 module contest.
