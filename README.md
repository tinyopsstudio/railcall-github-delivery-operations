# GitHub Delivery Operations for RailCall

[![Tests](https://github.com/tinyopsstudio/railcall-github-delivery-operations/actions/workflows/test.yml/badge.svg)](https://github.com/tinyopsstudio/railcall-github-delivery-operations/actions/workflows/test.yml)
[![RailCall Marketplace](https://img.shields.io/badge/RailCall-Marketplace-0f766e)](https://railcall.ai/marketplace/tinyops-studio-llc/github-delivery-operations)

This module fills the gap between opening a GitHub issue and shipping the
change. It adds ten governed operations for issue updates, pull requests,
review requests, merges, Actions dispatches, and repository file writes.

The module is free. It supports GitHub.com and HTTPS GitHub Enterprise API
bases.

Install it from the
[RailCall Marketplace](https://railcall.ai/marketplace/tinyops-studio-llc/github-delivery-operations).

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

RailCall already includes `github.list_issues` and `github.create_issue`.
Together, the built-ins and this module cover a practical issue-to-delivery
workflow without replacing GitHub's own review controls.

## Install

```bash
railcall market install tinyops-studio-llc/github-delivery-operations
```

Restart Studio or reload modules after installation.

The published `module.json`, `module.sig`, and `handlers/handler.py` in this
repository are the exact signed runtime bundle for marketplace version
`1.0.0`. The surrounding tests and documentation are published for independent
review.

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
- Actions: write
- Contents: read and write

GitHub administrators can narrow those permissions further when only a subset
of commands is needed.

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

The release was validated through three layers:

- 17 unit and bundle tests, including exact Ed25519 signature verification
- A clean marketplace install accepted all ten commands without rejection
- A live disposable-repository cycle exercised issue reads and writes, file
  writes, pull-request creation and merge, and a successful GitHub Actions
  dispatch

The CI workflow reruns the public test suite on Python 3.11, 3.12, and 3.13.
Live tests are intentionally excluded because they require a private GitHub
token and a disposable repository.

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
all ten commands load before publishing.

## Scope

This module deliberately omits administrator, billing, secret-management, and
repository deletion actions. Those are not necessary for the issue-to-delivery
workflow and would enlarge the trust surface without improving the core use
case.

Built by TinyOps Studio LLC for the RailCall 2026 Q3 module contest.
