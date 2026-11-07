# Communication Design: reply tiers, humanizer, style lint

**Date:** 2026-10-02
**Status:** Approved in brainstorming
**Names (Plan 9, 2026-10-05):** Jarvis is The Foundry and Optimus the Foreman; CodingAgent and SystemMaintenance are the Coding and Maintenance Workcells; jarvis-* units, JARVIS_* variables and Jarvis-* trailers are foundry-*, FOUNDRY_* and Foundry-* (see 2026-10-05-foundry-rename-design.md §2).
**Extends:** `2026-09-30-vault-template-design.md` (§9 `CLAUDE.md` rules, §6.3 headless commands, §6.8 linter)

## 1. Problem

Replies in vault sessions often read like transcripts: long walls of text where the answer is buried, step-by-step narration of what was done, pasted command output, and every detail given equal weight. Notes the agents write (briefings, debriefs, wiki notes) carry the usual AI tells: not-X-but-Y contrasts, one-line closers, forced triads, dashes everywhere, inflated claims. The user has had good results with the humanizer skill and wants its rules applied in the vault, including to notes written by headless runs, which cannot load plugins or skills.

## 2. Decisions

| Topic | Decision |
|---|---|
| Scope | All vault sessions: chat replies (length tiers, anti-transcript rules) and written output (humanizer wording rules). Not the user's other projects. |
| Reply length | Tiers by reply type (§3), not a single cap. |
| Formatting | The existing "Scannable Layouts" rule stays. Humanizer applies to wording only; its formatting section (§D: bold, headings, quotes) is not applied. |
| Humanizer delivery | Vendored into the vault (MIT, with its license), used as a project skill interactively and read by headless note-writing commands before their final write (§4). |
| Style lint | Warning-only checks for measurable tells, built after §4 has run a few weeks so thresholds are tuned on real notes (§5). |
| Roadmap | §3–§4 are Plan 6 (Communication), after Plan 3. §5 is Plan 7 (Style lint), after Plan 6 has run a few weeks. |

## 3. Chat reply tiers (`CLAUDE.md`, new "Writing" section)

- **Quick answer:** 1–3 sentences.
- **Task report:** fits one screen (about 25 lines). The outcome comes first, then the decisions the user must make, then only the details that change what the user does next. No narration of steps taken. No pasted command output unless it is the evidence for a claim, and then at most about 5 lines.
- **Document:** plans, specs and long reports go to a file (or an artifact) and are linked with a 1–3 sentence summary; never pasted into chat.

The section also carries about 10 condensed wording rules from humanizer's sections A, B, C and E: no not-X-but-Y contrasts, no one-line closers or dramatic fragments, no staged run-ups before the point, no forced triads, dashes used sparingly, plain words over stock AI vocabulary, no inflated significance or sales language, no chatbot residue ("Great question", "I hope this helps"). These apply to chat and to every note.

`CLAUDE.md` is appended to every headless run's system prompt, so headless runs get the condensed rules too.

## 4. Vendored humanizer (Plan 6)

- **Files:** `.claude/skills/humanizer/SKILL.md` and `.claude/skills/humanizer/LICENSE`, copied unchanged from humanizer v3.0.0 (MIT). The version is recorded in the README; updating it is a manual copy, carried to other vaults by `update_template.sh`.
- **Interactive:** available as `/humanizer` in vault sessions (project skill).
- **Headless:** `ingest`, `brief` and `debrief` gain a final step: Read `.claude/skills/humanizer/SKILL.md` and edit the draft against its sections A, B, C and E (wording), not D (formatting), keeping every fact, name, number and date. Read is already allowed inside the vault; no new Bash permission is needed. Notes written to staging still pass the publish gate unchanged; the shrink guard (body ≥ 60%) bounds how much an edit may cut.
- **Cost:** about 5k extra input tokens per headless run (the file is ~374 lines). Measured during acceptance.
- **Tests:** `commands.bats` checks that the three headless commands name the skill path and exclude section D, and that the skill and license files ship. `vault_integrity.bats` checks the vendored file's version line. The Plan 4a live acceptance steps are re-run, and must still pass with 0 permission denials.

## 5. Style lint (Plan 7)

- New warning-level issue codes in `vault_index.py issues`, for `wiki/` and `briefings/` notes only (never `raw/`):
  - `style-dashes`: em or en dashes above a density threshold per 1,000 words;
  - `style-contrast`: "not X but Y" and "isn't X, it's Y" constructions;
  - `style-stock-words`: humanizer §12's stock AI words above a count threshold.
- Warnings only: never an error, so they never block a commit or a publish. Reported by `lint_vault.sh` and `/lint`.
- Thresholds are set from the distribution in real notes after Plan 6 has run a few weeks. Each check gets fixtures with positive and negative examples in pytest.

## 6. Out of scope

- The user's other projects and user-level `~/.claude` settings.
- Rewriting existing notes in bulk; notes improve as they are patched.
- Formatting rules (bold, headings, tables).
- Blocking on style.
