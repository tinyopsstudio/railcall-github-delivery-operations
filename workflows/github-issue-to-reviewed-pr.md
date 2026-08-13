Convert an approved GitHub issue into a review-ready pull request without surrendering control of the repository.

The workflow reads the source issue, creates a work branch only when the expected source SHA still matches, writes one approved file change, opens a pull request, optionally routes it to users or teams, and reads the latest checks for the exact delivered commit.

Every GitHub mutation requires human approval. Source drift stops branch creation. Reviewer routing is optional. The workflow deliberately contains no merge step, so the repository owner retains the final integration decision.

Requires the free `tinyops-studio-llc/github-delivery-operations` RailCall module and repository-scoped GitHub credentials in the RailCall execution environment.
