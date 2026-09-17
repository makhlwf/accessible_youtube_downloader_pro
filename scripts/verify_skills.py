#!/usr/bin/env python3
"""
Skill Specification & SDO Validator
Validates that all skills in .agents/skills/ strictly adhere to the latest
agentskills.io and Antigravity specification:
- YAML frontmatter with 'name' and 'description'
- Description strictly starts with 'Use when...' and focuses on triggers/symptoms
- Description does NOT summarize workflow/process (SDO anti-pattern prevention)
- Word count and character limits are respected
- Required markdown sections are present
"""

import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / ".agents" / "skills"

REQUIRED_SECTIONS = [
    "## Overview",
    "## When to Use",
    "## Core Patterns & Invariants",
    "## Quick Reference",
    "## Implementation Procedures",
    "## Common Mistakes & Anti-Patterns",
    "## Verification & Quality Gates",
]

# Words that indicate workflow summarizing in description (SDO violation)
PROHIBITED_WORKFLOW_PATTERNS = [
    r"\bdispatches\b",
    r"\bstep 1\b",
    r"\bfirst .* then\b",
    r"\bfollowed by\b",
]


def validate_skill(skill_dir: Path) -> list[str]:
    errors = []
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return [f"Missing SKILL.md in {skill_dir.name}"]

    content = skill_file.read_text(encoding="utf-8")

    # Frontmatter check
    if not content.startswith("---"):
        return [f"{skill_dir.name}: Missing YAML frontmatter start ('---')"]

    parts = content.split("---", 2)
    if len(parts) < 3:
        return [f"{skill_dir.name}: Malformed YAML frontmatter"]

    frontmatter = parts[1].strip()
    body = parts[2].strip()

    # Name check
    name_match = re.search(r"^name:\s*([a-zA-Z0-9_-]+)", frontmatter, re.MULTILINE)
    if not name_match:
        errors.append(
            f"{skill_dir.name}: Missing or invalid 'name' field in frontmatter"
        )
    else:
        name = name_match.group(1).strip()
        if name != skill_dir.name:
            errors.append(
                f"{skill_dir.name}: Frontmatter name '{name}' does not match directory name '{skill_dir.name}'"
            )

    # Description check
    desc_match = re.search(
        r"^description:\s*(?:>-\s*|>\s*|\|\s*)?\n?(.*?)(?=\n[a-zA-Z0-9_-]+:|\Z)",
        frontmatter,
        re.DOTALL | re.MULTILINE,
    )
    if not desc_match:
        errors.append(f"{skill_dir.name}: Missing 'description' field in frontmatter")
    else:
        desc = " ".join(desc_match.group(1).split()).strip()
        if not desc.startswith("Use when"):
            errors.append(
                f"{skill_dir.name}: Description must start with 'Use when...' (found: '{desc[:30]}...')"
            )

        if len(desc) > 500:
            errors.append(
                f"{skill_dir.name}: Description exceeds 500 characters ({len(desc)} chars)"
            )

        for pattern in PROHIBITED_WORKFLOW_PATTERNS:
            if re.search(pattern, desc, re.IGNORECASE):
                errors.append(
                    f"{skill_dir.name}: Description appears to summarize workflow (matches '{pattern}')"
                )

    # Required sections check
    for sec in REQUIRED_SECTIONS:
        if sec not in body:
            errors.append(f"{skill_dir.name}: Missing required section '{sec}'")

    return errors


def main() -> int:
    if not SKILLS_DIR.exists():
        print(f"Error: {SKILLS_DIR} does not exist.")
        return 1

    skill_dirs = [d for d in SKILLS_DIR.iterdir() if d.is_dir()]
    if not skill_dirs:
        print(f"No skills found in {SKILLS_DIR}.")
        return 1

    total_errors = []
    print(f"Validating {len(skill_dirs)} skills in {SKILLS_DIR}...")

    for skill_dir in sorted(skill_dirs):
        errs = validate_skill(skill_dir)
        if errs:
            print(f"❌ {skill_dir.name}:")
            for e in errs:
                print(f"   - {e}")
            total_errors.extend(errs)
        else:
            print(f"✅ {skill_dir.name}: Valid agentskills.io format")

    if total_errors:
        print(f"\nValidation failed with {len(total_errors)} error(s).")
        return 1

    print("\nAll skills passed validation successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
