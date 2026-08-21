GitHub Issue to Reviewed Pull Request is a runnable, capability-scoped RailCall workflow for teams that want a controlled path from an approved issue to a review-ready pull request.

The v1.1.2 workflow ships an executable `engine_spec` with typed nodes and explicit edges. RailCall can render the per-run context form, plan the complete DAG, show the GitHub blast radius, enforce the declared zero-dollar spend ceiling, require human approval for every repository mutation, and issue signed receipts for each node.

What the workflow does:

1. Reads the approved source issue.
2. Creates a work branch only when the operator-supplied source SHA still matches.
3. Writes one approved file change with the supplied commit message.
4. Opens a review-ready pull request against the selected base branch.
5. Optionally requests reviews from named users or teams.
6. Reads the latest check runs for the exact delivered commit.

Built-in controls:

- Declared provider scope: GitHub only.
- Declared spend ceiling: 0 cents.
- Human approval remains required for branch creation, content writes, pull-request creation, and reviewer routing.
- Source drift causes branch creation to fail closed.
- Credentials stay in the buyer's RailCall vault.
- The workflow contains no merge command, so repository owners retain the final integration decision.

Worked example:

Provide issue number `42`, source branch `main`, the current 40-character source SHA, work branch `codex/issue-42`, one file path and approved content, a commit message, pull-request title and body, base branch `main`, and optional reviewer lists. RailCall plans the six-node run first. After the operator reviews and approves the plan, each GitHub action executes through the companion module and produces receipt-backed evidence.

Requirements:

- RailCall station v0.51 or later for executable workflow support.
- Free companion module `tinyops-studio-llc/github-delivery-operations` v1.2.0 or later.
- Repository-scoped GitHub credentials configured in the RailCall vault with only the permissions required for the chosen actions.

The linked demo video shows the companion GitHub module and its governed execution model.

For teams that want implementation support, TinyOps offers a $499 managed setup for one repository. It includes a least-privilege permission map, approval rules, smoke-test evidence, and an operator runbook. GitHub credentials remain in the client's own RailCall vault.
