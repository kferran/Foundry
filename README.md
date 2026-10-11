<!-- foundry:landing -->
# The Foundry

An Obsidian + Claude Code "second brain" vault template. It runs on Linux (Arch or Debian), on one machine or as a server that syncs with laptop clients.

- **The vault compiles itself.** Files you drop in, short digests of your Claude Code sessions and your meetings become a wiki of concepts, entities and summaries, split into `work`, `personal` and `shared` partitions.
- **It runs your day.** A morning brief from your calendar, open loops, alerts and production errors; an evening debrief of what you delivered.
- **Automation stays checked.** Timed headless `claude -p` runs write to a staging area, and a deterministic gate validates and publishes their output.

## Quick start

1. Install what [the manual's Requirements](FOUNDRY.md#requirements) lists and sign in to Claude Code.
2. Create your vault from this template and start Claude Code in it:

   ```sh
   git clone <template-url> my-vault    # or "Use this template" on the hosting site
   cd my-vault
   claude
   ```

3. Paste the setup prompt from [the manual's Getting started](FOUNDRY.md#getting-started) with your answers, or type `/setup` and answer its questions.

`/setup` replaces this page with your vault's own README, which describes your machines, codebases and what runs where. Template updates keep it.

## The manual

Everything else (how it works, daily use, memory, machine roles, security and updating) is in [FOUNDRY.md](FOUNDRY.md).
