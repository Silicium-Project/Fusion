# Branching workflow (issues → branches → main)

This repo can auto-create one branch per GitHub issue, and auto-merge to `main` only when CI is green.

## 1) Issue → branch

Workflow: `.github/workflows/issue-branch.yml`.

When an issue is opened/reopened, it creates:

- `issue-<number>-<slug>`

and comments the issue with the branch name.

## 2) Work on the branch

Checkout locally and commit normally:

```bash
git switch issue-123-some-title
```

Open a PR targeting `main`, and include `Fixes #123` in the PR description so GitHub closes the issue on merge.

## 3) Merge only if tests pass

Two parts:

- Branch protection on `main` requiring your CI checks (server-side enforcement).
- Auto-merge (optional): add the `automerge` label on the PR.

Workflow: `.github/workflows/automerge.yml` triggers when the `EntryPoint Tests` workflow completes successfully and merges PRs labeled `automerge`.

## 4) Close the branch

Workflow: `.github/workflows/delete-merged-branches.yml` deletes `issue-*` branches after a successful merge.

## Notes

- If GitHub-hosted Actions are disabled/billing-limited, these workflows must run on a self-hosted runner.

