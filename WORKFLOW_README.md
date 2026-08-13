# GitHub Issue to Reviewed Pull Request

This RailCall workflow converts a GitHub issue into a review-ready pull request while keeping every external write behind explicit human approval.

## What it does

1. Reads the source issue.
2. Creates a work branch only when the supplied source SHA still matches GitHub.
3. Writes one approved file change to that branch.
4. Opens a pull request against the selected base branch.
5. Optionally requests named users or teams as reviewers.
6. Reads the latest check runs for the exact delivered commit.

The workflow deliberately stops before merge. This keeps final repository integration with the team that owns the codebase.

## Governance

- Every GitHub mutation declares `approval: require_human`.
- Branch creation uses `expected_source_sha` to refuse execution after source drift.
- Check verification is pinned to the commit SHA returned by the file write.
- Reviewer routing is conditional, so teams can omit reviewers without breaking the run.
- No merge command appears in the workflow.
- No credential or repository secret is embedded in the workflow payload.

## Requirements

Install the companion module first:

```text
railcall market install tinyops-studio-llc/github-delivery-operations
```

The module requires `GITHUB_TOKEN`, `GITHUB_OWNER`, and `GITHUB_REPO` in the RailCall execution environment. Grant the token only the repository access needed for the run.

## Context example

```json
{
  "issue_number": 42,
  "source_branch": "main",
  "expected_source_sha": "0123456789abcdef0123456789abcdef01234567",
  "work_branch": "railcall/issue-42",
  "file_path": "docs/issue-42.md",
  "file_content": "Implementation notes for issue 42.\n",
  "commit_message": "docs: address issue 42",
  "pull_request_title": "Address issue 42",
  "pull_request_body": "Implements the approved scope from #42.",
  "base_branch": "main",
  "reviewers": ["octocat"],
  "team_reviewers": [],
  "reviewers_present": true
}
```

Replace the sample SHA and reviewer with values from the target repository. Set `reviewers_present` to `false` when no reviewer routing is needed.

## Marketplace

- Module: <https://railcall.ai/marketplace/tinyops-studio-llc/github-delivery-operations>
- Workflow: <https://railcall.ai/marketplace/tinyops-studio-llc/github-issue-to-reviewed-pr>

## Setup help

For teams that want this workflow configured and validated for one repository, TinyOps offers a [$499 managed setup](https://tinyopsstudio.com/railcall-github-delivery-operations-setup). The fixed scope includes a least-privilege permission map, approval rules, smoke-test evidence, an operator runbook, and one revision. GitHub credentials remain in the client's own RailCall vault.
