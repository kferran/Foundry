# Archive

Specs and plans of shipped work (owner, 2026-11-06, #527 step 3). They are records: kept for their design rationale, never edited, and skipped by `conformance.bats`.

A spec or plan moves here when its work has shipped and nothing still waits on it. It stays in `specs/` or `plans/` while any of these hold:
- an open pull request builds it;
- its feature is held, or waits on a trigger;
- a live check or baseline of its feature waits under the roadmap's "Waiting on the owner";
- a phase of it is still open on its issue;
- the #429 history rewrite names its path.

`docs/superpowers/specs/2026-09-30-vault-template-design.md` stays: `FOUNDRY.md` cites its sections.

The move rewrote each `docs/superpowers/specs/<file>` and `docs/superpowers/plans/<file>` path in the repository to its archive path, except in `changes/`. Issue and pull request text on GitHub still names the old paths, and the files keep their history under `git log --follow`.
