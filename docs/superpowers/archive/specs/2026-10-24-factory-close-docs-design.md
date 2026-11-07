# Factory close-out: one inventory of what the Foundry offers

**Date:** 2026-10-24
**Status:** approved (owner, 2026-10-24; spec merged in #381) and built in the pull request that follows it
**Program:** `docs/superpowers/2026-10-21-factory-plan.md` (the close-out, #331)
**Grill:** not an owner idea: the owner asked for it on 2026-10-21, https://github.com/kferran/Foundry/issues/331
**Builder check:** 2026-10-24, five questions and seven fact corrections, all settled as my calls (none needed the owner): the README anchors get their own check, the link test stays as it is (§3.4); the unit and extension cases read only the new section (§3.4); old records get a "since raised" note, never a rewrite (§3.5); all six F-spec status lines are corrected (§3.5); "Turn on" names whatever turns a feature on, the role and the hooks included (§3.1).
**Blueprint:** none: documentation and one docs test; no new feature shape.
**Lane:** docs, one pull request, no separate plan (small: one manual, one README, one test). It touches no safety surface, so it auto-merges on green CI.

## 1. Why

The owner asked on 2026-10-21 that, when the factory is in place, the documentation say what is available in the Foundry. F0 to F5 are merged. Today FOUNDRY.md (506 lines) lists the parts in seven places and none of them is complete:

- **Status, "Works today"** (FOUNDRY.md:19-27) names two of the four extensions (handoffs, telemetry; intraday and health are missing).
- **Daily use** (:65-78) has the commands, but not `/new-source` or `/foundry-review`.
- **Feature paragraphs** (:80-135) give each feature's config key inline, in prose.
- **The layout tree** (:205) names the core units only; `foundry-telemetry` appears nowhere, and `foundry-watch.timer` only in the intraday paragraph (:86).
- **Architecture and Development** (:349-488) hold the factory line, but in four sections with no entry point, and no section says how to add a Source.

The existing drift test (`vault_integrity.bats:284`, `manual_drift` at :269-282) checks commands, core skills, Workcells and core units. It misses extension skills (`/rca`), extensions and extension units, which is how the gaps above got in.

## 2. Goals, non-goals, anti-goals

- **Goals:**
  - A vault user reads one section and knows every feature the Foundry has, how to turn it on, what runs it and where its output shows up.
  - A builder reads one section and knows how a feature is built on the line, ending with how to add a Source.
  - A test fails when a command, skill, extension or unit ships without its row.
- **Non-goals:**
  - Rewriting the feature paragraphs (:80-135); they stay as the detail the table links to.
  - The vault's own README; `/setup` writes that.
  - New config keys or behavior changes.
- **Anti-goals:**
  - A second copy of facts that live in one place already. The table points at a paragraph; it does not restate it.
  - A test that checks wording. It checks names only.

## 3. Design

### 3.1 FOUNDRY.md: "What the Foundry offers"

A new `##` section after "How it works" (:34), replacing the Status section's "Works today" bullets (:19-27). The Status section keeps its other lines and links to the new section. Three tables:

1. **Features**, one row each: `| Feature | What it does | Turn on | Runs as | Smoke row | Output |`.
   - **Core rows:**
     - intake and `/ingest`
     - the brief
     - the debrief
     - memory (the session hooks)
     - the Now page
     - Work Orders
     - meetings
     - inbox triage, mail and chat
     - Slack notices
     - sync
     - the template update
     - the smoke check
   - **One row per extension:** handoffs, health, intraday, telemetry with RCA.
   - **"Turn on"** names whatever turns the feature on:
     - a config key, for example `meetings_enabled: true` or `triage_chat_enabled`;
     - the machine role, for the brief, debrief, intake, smoke and sync (`machine_role`; sync on a server only);
     - `install_hooks.sh`, for memory;
     - `extensions: [<name>]`, for an extension.

     `orders_enabled` and `update_enabled` are on when absent, so a vault made before they were opt-in keeps both (`install_units.sh:108-109`), while `config.example.md` starts a new vault with both off and `/setup` asks; the row says both.
   - **"Runs as"** is the unit's base name in backticks (`` `foundry-watch` ``), or "none" (health, handoffs).
   - **"Output"** names the brief or debrief section, the alert tag, or the Slack notice.
   - Each Feature cell links the paragraph below that explains it.
2. **Commands and skills**: the Daily use table (:65-78) stays where it is and gains `/new-source` and `/foundry-review` (builder skills, marked as such). `/rca` is already in it.
3. **Extensions**, one row each: `| Extension | Needs | Connectors | Config keys | Commands and skills |`.
   - The rows come from each `extension.md` (`requires`, `deps`, `sources`) and its `schemas/config.md`.
   - For example: telemetry needs handoffs and `az`; intraday needs the Slack, Gmail and Google Calendar connectors.

### 3.2 FOUNDRY.md: "The factory line" entry point

Development (:396) gains one short `### The factory line` subsection at its top. It lists the line in order, one line each, linking the section that holds the detail; it copies none of it:

- the blueprints (Architecture :365)
- the standard parts: the homes `conformance.bats`'s `PART_HOMES` lists (`vaultlib/connector.py`, `lib_fetch.sh`, `vaultlib/config.py`, `stub_claude_connector`), plus `vaultlib/api.py`, the one module an extension imports (F2)
- the stations and their skills (:400)
- the conformance gates (the `conformance.bats` and `vault_integrity.bats` tests by name)
- the defect labels (:415)

It ends with **Add a Source**, in five lines or fewer. The grill and the spec come from the pipeline (FOUNDRY.md:402-403, :412); the rest comes from `.claude/skills/new-source/SKILL.md`:

1. Grill the idea.
2. Write the spec with `Blueprint: Source`.
3. Run `new-source`.
4. Fill in the query and the brief section.
5. Run `foundry-review` before the pull request.

### 3.3 README

The template's `README.md` (27 lines) gains two links next to its existing pointer (:27): "What the Foundry offers" and "Building on the line", each to the new section's anchor. It stays a landing page.

### 3.4 The drift test

`manual_drift` (`vault_integrity.bats:269-282`) gains three cases. Two of them read only the "What the Foundry offers" section (from its heading to the next `## `), so a mention elsewhere in the manual cannot satisfy them:

- each `extensions/<name>/` must appear in that section as a `` | `<name>` | `` row (the Extensions table)
- each `extensions/*/units/foundry-*.service.in` must appear in that section as `` `foundry-<name>` ``
- each `extensions/*/skills/*/SKILL.md` must appear as `` `/<name>` `` anywhere, as core skills do

The core-unit case keeps reading the layout tree's `systemd/` line. The README's two links get their own check: each anchor matches a FOUNDRY.md heading. The shared relative-link test (:257) strips anchors and stays as it is. The paired seeded-failure test (:291) gains one seed per new case: an extension row removed, `/rca` renamed, the `foundry-watch` cell removed (which must fail even though :86 still names `foundry-watch.timer`), and a README anchor renamed. The test still skips in a vault.

### 3.5 Stale claims corrected on the way

- FOUNDRY.md:5 and :29 call the preference notes and the Foreman still to come; both are merged (roadmap: #96, #82). Correct both lines.
- FOUNDRY.md:366 says "F1 moves…": past tense, F1 closed (#306).
- `2026-10-21-factory-plan.md`: tick F0 to F5's done items and the S track's merged ones. F4's `connector-probe` and `live-acceptance` stay open.
- `2026-10-17-cto-gap-plan.md:14` and :109, and roadmap :52, give the line budget as 13,950 and 13,800. Those lines record decisions, so each gets the file's own note form, "(since raised to 15,100 by #373)", and the old figure stays.
- The six factory specs (F0 to F5) still read `**Status:** draft for the owner`. Each becomes `**Status:** approved and built (<the PRs>)`.

- `.claude/skills/new-source/SKILL.md` says the brief prompt has 5 words left; since F5 it has none (found while building).

## 4. Done when

| Check | Test |
|---|---|
| every command, skill (core and extension), Workcell, extension and unit (core and extension) on disk has its row | `manual_drift` on FOUNDRY.md passes; each seed fails it |
| README links both new sections, and each anchor matches a FOUNDRY.md heading | the new anchor check in `manual_drift`'s test; its seed fails it |
| the stale claims in §3.5 are corrected | read in review |
