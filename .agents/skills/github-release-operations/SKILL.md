---
name: github-release-operations
description: >-
  Use when automating GitHub release creation, binary asset uploads,
  tag management, changelog generation, or repository administrative tasks via GitHub CLI or API.
---

# GitHub Release Operations & Accessible Repository Administration

## Overview

GitHub's web UI presents significant accessibility barriers for blind developers (drag-and-drop file upload zones, unlabelled icon buttons, and complex Monaco editors). This skill guides agents and developers in using the GitHub CLI (`gh`) and REST API to manage releases, upload binary installer assets (`HexPlayer_Setup.exe`), manage Git tags, and generate release notes with 100% keyboard and screen reader accessibility.

## When to Use

- Publishing a new HexPlayer release on GitHub.
- Uploading compiled Windows installer binaries (`.exe`) and checksum files.
- Managing Git release tags and generating changelogs from merged PRs.
- Automating repository settings, collaborators, or branch protection via the GitHub CLI.
- Assisting visually impaired maintainers with repository release workflows.

**When NOT to use:**
- Local binary compilation (use `windows-build-packaging`).

## Core Patterns & Invariants

### 1. Bypassing Drag-and-Drop via `gh release` CLI
Never require maintainers to use the GitHub web drag-and-drop upload zone. Use the official GitHub CLI (`gh`):

```powershell
# ✅ REQUIRED: Programmatic release creation and asset upload
gh release create v4.6.0 `
    dist/HexPlayer_Setup.exe `
    update.json `
    --title "HexPlayer v4.6.0" `
    --notes-file release_notes.md `
    --latest
```

### 2. Auto-Generating Release Changelogs
Extract merged pull requests and commits since the previous release tag:

```powershell
gh release create v4.6.0 --generate-notes
```

### 3. Binary Asset Upload to Existing Releases
When uploading post-build artifacts (e.g. portable zip bundles):

```powershell
gh release upload v4.6.0 dist/HexPlayer_Portable.zip --clobber
```

### 4. Semantic Version Tagging Protocol
Verify `pyproject.toml` version matches the Git release tag:
- Read version: `uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"`
- Git tag: `git tag -a v4.6.0 -m "Release v4.6.0"`
- Push tag: `git push origin v4.6.0`

## Quick Reference

| Action | GitHub CLI (`gh`) Command |
| :--- | :--- |
| **List Releases** | `gh release list --limit 5` |
| **View Release Details**| `gh release view v4.6.0` |
| **Create Release + Upload**| `gh release create <tag> <files...> --title <title> --notes <notes>` |
| **Upload Extra Asset** | `gh release upload <tag> <file> --clobber` |
| **Delete Asset** | `gh release delete-asset <tag> <asset-name>` |
| **Draft Release** | `gh release create <tag> <files...> --draft` |

## Implementation Procedures

### Step 1: Performing an End-to-End Release
1. Run preflight verification: `uv run python scripts/agent_preflight.py`.
2. Package Windows installer: `.\BuildNPackage.bat`.
3. Check generated binaries in `dist/`.
4. Create the GitHub release and upload assets:
   ```powershell
   gh release create v4.6.0 dist/HexPlayer_Setup.exe update.json --title "HexPlayer v4.6.0" --generate-notes
   ```
5. Confirm release status:
   ```powershell
   gh release view v4.6.0
   ```

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Telling screen reader users to drag-and-drop | Inaccessible for blind maintainers | Use `gh release upload` CLI |
| Version mismatch between tag and `pyproject.toml` | Confuses in-app updater and users | Align tag with `pyproject.toml` |
| Uploading assets without `--clobber` on retry | Fails with duplicate asset name error | Use `--clobber` to overwrite |
| Releasing without running preflight | Publishes broken builds or failing tests | Always verify with `agent_preflight.py` first |

## Verification & Quality Gates

- **CLI Authentication**: Run `gh auth status` to confirm GitHub permissions.
- **Tag Validation**: Confirm Git tag exists locally and on remote (`git tag -l`).
- **Asset Confirmation**: Run `gh release view <tag>` to verify download URLs and asset sizes.
