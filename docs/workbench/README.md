# Workbench and member app

Issue specs for [ADR 0001](../decisions/0001-desktop-first-workbench.md): a desktop-first planner
workbench, a mobile-first member area on the web, and a native member app built with Expo.

- `issues/NN-*.md`: one spec per GitHub issue. The front matter holds the title and labels; the
  body is identical to the GitHub issue body. Each spec ends with an **Implementation prompt** that
  can be pasted into an agent (Cursor, Claude Code) as it is.
- `created-issues.json`: spec prefix to GitHub issue number. All issues are sub-issues of #107.

The order and dependencies are in the ADR's **Work plan** table. The standing rules for working any
of these issues are in `AGENTS.md` under **Working an issue**; the frontend rules are under
**Style → Frontend surfaces**.

When a spec changes, update the GitHub issue body in the same change so the two never disagree.
