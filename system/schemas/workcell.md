---
type: schema
schema_for: workcell
folders: ["system/agents/workcells/"]
fields:
  type: {kind: const, value: workcell, required: true}
  capabilities: {kind: list, of: string, required: true}
---
# Workcell
A specialist agent, one file per Workcell. `capabilities` lists the work it takes; work goes to the Workcell that declares the capability it needs, never to a Workcell by name. The body's first heading is the display name. Each capability matches `^[a-z]+(-[a-z]+)*$` and is declared by one Workcell only, and the `capability` values in `system/schemas/concept.md` are the union of every Workcell's `capabilities` (`vault_integrity.bats` checks all three). The Foreman (`system/agents/foreman.md`) has no frontmatter: it is addressed, not dispatched.
