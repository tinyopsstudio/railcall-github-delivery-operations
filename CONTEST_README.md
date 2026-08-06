# GitHub Delivery Operations for RailCall

**Contest category:** New integration
**Marketplace:** [GitHub Delivery Operations](https://railcall.ai/marketplace/tinyops-studio-llc/github-delivery-operations)

## Who it helps

This free module is for small engineering and operations teams that manage delivery work in GitHub. It keeps issue updates, branch creation, pull requests, guarded merges, Actions runs, checks, and file changes inside RailCall's preview -> approve -> execute -> signed receipt loop.

The module adds 18 commands. A team can move from an issue through a reviewed change and CI evidence without passing a GitHub token in command inputs. It supports GitHub.com and HTTPS GitHub Enterprise API bases.

## Install and credentials

```bash
railcall market install tinyops-studio-llc/github-delivery-operations
```

Save one local RailCall vault entry named `github`:

```json
{
  "token": "YOUR_TOKEN",
  "owner": "your-org",
  "repo": "your-repo"
}
```

Use a fine-grained token or GitHub App token limited to the commands you need. Typical permissions are Metadata read, Issues read/write, Pull requests read/write, Contents read/write, Actions read/write, and Checks read. Credentials stay in the vault and are excluded from command inputs, results, receipts, and logs.

## Working example

```bash
railcall run github.get_issue --issue_number=7
```

Expected result shape:

```json
{
  "ok": true,
  "http_status": 200,
  "issue": {
    "number": 7,
    "title": "Ship module",
    "state": "open",
    "labels": ["delivery"]
  }
}
```

Every write is previewed and requires approval. Reads use bounded retries for temporary failures. Writes run once and fail closed when GitHub cannot confirm the result. Branch creation and pull-request merges can verify an expected SHA to reject stale approvals.

## Quality and limits

The signed v1.1 bundle passes 25 tests on Python 3.11, 3.12, and 3.13. A clean marketplace install loaded all 18 commands, and live smoke tests exercised real GitHub branch and Actions APIs.

One vault entry targets one repository. The module uses GitHub REST APIs and does not cover Projects v2, releases, deployments, or organization administration. GitHub permissions and branch rules can still reject an approved write with a clear error.

Source, CI, and full reference documentation are available in the [public repository](https://github.com/tinyopsstudio/railcall-github-delivery-operations).

`contest:2026Q3`
