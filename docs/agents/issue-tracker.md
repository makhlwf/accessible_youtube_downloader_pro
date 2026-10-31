# Issue tracker: GitHub

Issues and specs live in GitHub Issues for
`makhlwf/accessible_youtube_downloader_pro`. Use the `gh` CLI.

## Repository targeting

Run commands from this clone. Before the first issue write in a session,
check `gh repo view --json nameWithOwner`.

The target must be `makhlwf/accessible_youtube_downloader_pro`.
If it differs, stop and confirm with the user. Use
`--repo makhlwf/accessible_youtube_downloader_pro` to target it explicitly.

## Conventions

- Create: `gh issue create --title "..." --body "..."`.
  For multiline bodies, use `--body-file` with a UTF-8 file or standard input.
- Read: `gh issue view <number> --json number,title,body,labels,comments`.
- List: `gh issue list --state open --json number,title,body,labels`.
  Add label and state filters as needed; account for pagination when a
  complete inventory is required.
- Update: `gh issue edit <number> --body-file <file>`.
- Comment: `gh issue comment <number> --body "..."`.
- Apply or remove labels: `gh issue edit <number> --add-label "..."`
  or `--remove-label "..."`. Read `docs/agents/triage-labels.md` for mappings.
- Close: post the explanation with `gh issue comment`, then run
  `gh issue close <number>`. Keep commenting separate from closing so an
  explanation can also be posted to an already-closed issue.

## Parent issues and blockers

- Create a child with `gh issue create --parent <parent> ...`,
  or link an existing child with
  `gh issue edit <parent> --add-sub-issue <child>`.
- Record dependencies with
  `gh issue edit <child> --add-blocked-by <blocker>`.
- If native relationships are unavailable, put `Part of #<parent>` or
  `Blocked by: #<number>` at the top of the child body. Also list fallback
  children in the parent's task list.
- A ticket is unblocked only when every blocking issue is closed.

## Pull requests as a triage surface

**PRs as a request surface: no.**

## Skill instructions

When a skill says "publish to the issue tracker", create a GitHub issue.
When it says "fetch the relevant ticket", read the issue and its comments.

## Wayfinding operations

- Keep the map in one issue labelled `wayfinder:map`, with Notes,
  Decisions-so-far, and Fog sections.
- Link child tickets to the map using the parent conventions above.
  Use `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`,
  or `wayfinder:task` as appropriate.
- Select the first open child in map order with no open blocker and
  no assignee.
- Claim with `gh issue edit <number> --add-assignee "@me"`.
- Resolve by commenting with the answer, closing the child, and adding
  a summary and reference to the map's Decisions-so-far section.
