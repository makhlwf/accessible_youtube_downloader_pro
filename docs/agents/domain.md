# Domain docs

This repository uses a single-context layout.

## Before exploring

- Read root `GLOSSARY.md` for domain terminology, when present.
- Read relevant decisions in root `docs/adr/`, when present.

If these files or directories do not exist, proceed silently.
Do not suggest creating placeholders. The domain-modeling skill creates
documentation when terms or decisions are actually resolved.

## Layout

- `GLOSSARY.md`: shared vocabulary for HexPlayer.
- `docs/adr/`: architecture decision records for this repository.

## Use the glossary's vocabulary

Use defined terms in issue titles, proposals, hypotheses, and test names.
Avoid synonyms the glossary explicitly rejects.

If a concept is missing, reconsider whether it matches the project's
language. Note genuine vocabulary gaps for domain-modeling.

## Flag ADR conflicts

If a proposal contradicts an existing ADR, identify the decision and
explain why it should be reconsidered rather than silently overriding it.
