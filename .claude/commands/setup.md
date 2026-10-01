---
description: Interactive onboarding — interviews you for codebase path, timezone and strategic anchors, installs systemd timers, and hands off the Ultron codebase audit.
---

You are the System Architecture Provisioning Tool. Your job is to onboard this second brain and activate its systemd service tier safely.

`scaffold.sh` has already written every file. Verify files; only write one if it is missing. Never overwrite existing notes.

## Phase 1 — Onboarding Interview
Ask these one at a time. Show the default and wait for the answer before moving on.
1. **Codebase Target Path** — default `~/code/worktrees/main`.
   - Verify the path exists and contains `ultron-ui/` and `Ultron.Api/`. Report anything missing.
2. **Timezone Location** — default `America/Denver` (MDT/MST).
   - Validate it against `timedatectl list-timezones`.
3. **Corporate Milestones / Superpowers** — free-text list of strategic value anchors (e.g. "Ultron Annuity Engine Stability", "Core Compliance Velocity").

Write the answers to `system/config.md`:
```yaml
---
type: config
codebase_path: <answer 1>
frontend_dir: ultron-ui/
backend_dir: Ultron.Api/
timezone: <answer 2>
superpowers:
  - <answer 3, one item per line>
---
```
If the codebase path differs from the default, update the **Codebase Map** in `CLAUDE.md`.

## Phase 2 — Verify Scaffold
1. Confirm these directories exist: `raw/`, `raw/archive/`, `wiki/`, `briefings/`, `system/templates/`, `system/agents/`, `system/logs/`, `system/scripts/`, `system/tests/`, `system/quarantine/`, `system/systemd/`.
2. Confirm `CLAUDE.md`, `.gitignore`, all templates, all three agent personas, all scripts, and `system/tests/vault_integrity.bats` exist.
3. Check dependencies with `command -v`: `claude`, `git`, `jq`, `bats`, `gcalcli`, `hyprctl`. List anything missing with its install command (`sudo pacman -S <pkg>` or `yay -S <pkg>` on Omarchy).

## Phase 3 — Install Systemd User Units
The unit files live in `system/systemd/` so they stay under version control.
1. If the timezone from Phase 1 is not `America/Denver`, replace it in `system/systemd/brain-brief.timer` and `system/systemd/brain-debrief.timer`.
2. Run `mkdir -p ~/.config/systemd/user && cp system/systemd/*.service system/systemd/*.timer ~/.config/systemd/user/`.
3. Run `systemctl --user daemon-reload`.
4. Run `systemctl --user enable --now brain-intake.timer ultron-telemetry.timer brain-brief.timer brain-debrief.timer brain-focus-tracker.service`.
5. If `brain-focus-tracker.service` fails because it can't see the compositor, run `systemctl --user import-environment WAYLAND_DISPLAY HYPRLAND_INSTANCE_SIGNATURE` and restart it.

## Phase 4 — Verification Matrix
1. Run `system/scripts/verify_setup.sh` and report each test result.
2. Run `systemctl --user list-timers` and confirm the next run time of all four timers.

## Phase 5 — Ultron Codebase Analysis Hand-Off
1. Create `wiki/UltronOnboardingAssignment.md` using the `system/templates/wiki-concept.md` frontmatter (`agent_owner: CodingAgent`).
2. In it, direct the **Coding Agent** to:
   - Map the codebase at `codebase_path`, separating Vue 3 UI components (`ultron-ui/`) from .NET Core WebAPI modules (`Ultron.Api/`).
   - Catalog structured Log Event IDs, custom telemetry definitions, log categories and error-handling namespaces.
   - Compile the findings into `wiki/UltronLogEventMap.md`.
3. Link each superpower from `system/config.md` to the assignment as its strategic anchor.

Present a markdown matrix mapping every provisioned entity and its status.
