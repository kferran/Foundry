# Server brief noise: focus is not tracked here

**Date:** 2026-10-11
**Status:** A fix (fast lane, `2026-10-11-fast-lane-design.md`): this page is its record; no plan.
**Issue:** none yet; open one with the sentence below when the fix ships.

## 1. The wrong behaviour

On a server, the brief lists "focus_yesterday: no focus log for <date>" under Unavailable Sources every day, and the debrief lists "focus" the same way. The focus tracker (`track_obsidian.sh`) needs Hyprland and runs only on a standalone machine (`install_units.sh` enables `foundry-focus.service` for standalone only). On a server the source can never exist, so the line is noise that hides real unavailable sources.

## 2. The fix

- `brief_prep.sh` and `debrief_prep.sh`: when `machine_role` is `server`, write an empty `focus_yesterday.md` (or `focus.md`) and no `prep_unavailable` line for focus. Standalone behaviour is unchanged.
- `brief.md` and `debrief.md`: when the focus file is empty and the role is `server`, the Focus Drift line reads "Focus: not tracked on a server." The commands already read `machine_role` for other rules; where they do not, `brief_prep.sh` writes the line into the file itself so the command copies it.

## 3. Test

`prep.bats`: with `machine_role: server`, `brief_prep.sh` writes no `focus_yesterday` line to `unavailable.md` and `focus_yesterday.md` holds the "not tracked" line; with `standalone` and no log, the unavailable line is written as today. `debrief_prep.sh` the same for `focus.md`. Each fails before the change. Bound tools: bats (`prep.bats`) and the gate.

## 4. Out of scope

- A focus tracker for a client machine or for a desktop other than Hyprland.
- Removing the Focus Fragmentation rule from `CLAUDE.md` (the CLAUDE.md prune spec covers it).
