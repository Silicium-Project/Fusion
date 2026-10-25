# Backlog Hygiene Policy

This policy defines how Silicium parent/umbrella issues are created, maintained, and closed.

## Scope

- Parent issues (epics/umbrellas) that track multiple child issues.
- Legacy issues that became redundant after scoped child delivery.

## Parent Issue Rules

1. A parent issue must include explicit child issue links (checklist format preferred).
2. A parent issue must define clear closure criteria (what “done” means).
3. A parent issue must define review cadence (weekly or per milestone).
4. If scope changes, parent issue must be re-scoped with a summary comment.
5. If superseded, parent issue must be closed with:
   - replacement issue link(s),
   - rationale,
   - migration note.

## Closure Policy

Close a parent issue when one of these is true:

- All linked child issues are closed and closure criteria are met.
- The parent is superseded and a replacement issue is linked.
- The parent is redundant (duplicate scope already delivered elsewhere).

When closing, add a final summary comment:

- what was delivered,
- which issues/commits cover the scope,
- what remains (if any).

## Hygiene Checklist (Weekly or Milestone)

- Review open parent issues and child completion ratios.
- Close or re-scope stale parent issues.
- Verify no duplicate umbrella scope exists.
- Post/update an audit note in `docs/backlog-audit-YYYY-MM-DD.md`.

## Template Reference

Use `.github/ISSUE_TEMPLATE/parent-umbrella.md` for new parent issues.
