# Task tracking

Use [GitHub Issues](https://github.com/trusohamn/repeto/issues) as the shared
backlog for work on Repeto. An open issue means work is still to be done; a
closed issue records completed work or a decision not to pursue it.

For now, use the issue list rather than a GitHub Project board: the backlog is
small enough to manage without maintaining a second view of status. Reconsider
a board if the backlog grows or coordinating work across issues becomes hard.

## Create an issue

1. Search existing open and closed issues to avoid duplicates.
2. Use a short, descriptive title and explain the goal and relevant context.
3. Add concrete acceptance criteria or steps to reproduce, as appropriate.
   Record open questions rather than assuming an implementation.
4. Apply existing labels when useful, such as `enhancement`, `bug`, or
   `documentation`. Do not use `publish-audio` as a task-category label: it
   authorizes paid audio generation when applied to an eligible PR.
5. Add a priority and its reason to the issue description when timing matters.
   Note dependencies or blockers and link the relevant issues.

Issues can be created through GitHub or with the GitHub CLI:

```sh
gh issue list --repo trusohamn/repeto --state all
gh issue create --repo trusohamn/repeto --title "Short task title" \
  --body "Goal and acceptance criteria" --label enhancement
```

## Pick up and track work

1. Review open issues and their priorities, dependencies, and assignees. Agree on
   what to tackle next; urgent or blocking work generally comes first. If
   priorities are unclear, ask the maintainer instead of guessing.
2. Assign the issue to the person taking responsibility. An unassigned issue
   is available to pick up; assignment indicates ownership, not completion.
3. Before changing files, check the current branch and working tree with
   `git status --short --branch`. Preserve unrelated changes. Create a separate
   branch from an up-to-date `main`, for example `docs/issue-27-task-workflow`;
   never push directly to `main`.
4. Discuss decisions, progress, and blockers in the issue so the context stays
   visible. Link related issues and pull requests. If ownership changes, update
   the assignee.
5. When the acceptance criteria are met and the work has been reviewed and
   merged, close the issue. If it will not be pursued, explain why before
   closing it. Reopen it if more work is needed.

## Review, commit, and propose changes

1. Run the relevant checks for the change. Review `git status --short` and
   `git diff`, including new files, for correctness, unrelated changes, and
   secrets. Never commit credentials or local environment files.
2. Stage only the intended files by naming them explicitly with
   `git add <path>`. Inspect the staged patch with `git diff --cached` and
   `git diff --cached --check`; leave unrelated work unstaged.
3. When authorized to commit, use a descriptive message that references the
   issue, for example `git commit -m "Document task workflow (#27)"`.
   A commit reference links the work but does not close the issue.
4. When authorized to open a PR, push the separate branch and open a PR into
   `main`. Describe the changes and checks, and include `Closes #<number>` in
   the PR description when its merge should close the issue. Do not close the
   issue just because a branch or PR was created.

An issue records a request; it does not authorize paid audio generation,
merging, deployment, or feed submission. Follow the separate approvals and
publication gates in [AGENT.md](../AGENT.md) and
[the deployment guide](deploy.md).
