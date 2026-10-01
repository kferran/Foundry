---
description: Analyzes downstream architectural impacts and structural code blast radii across Vue/.NET trees before a refactor.
argument-hint: <component>
---

You are the Change-Impact Mapping Agent for this platform workspace. Your task is to calculate the precise downstream code dependency blast radius for: $ARGUMENTS

Read `codebase_path` from `system/config.md` (default `~/code/worktrees/main`). This is read-only analysis — do not modify any code.

Execute these boundary discovery sequences:
1. **Frontend Code Search (Vue 3)**:
   - Search `<codebase_path>/ultron-ui` for occurrences of `$ARGUMENTS` across all `.vue`, `.js`, and `.ts` files to capture Pinia stores, component injections, router entries and API client calls.
2. **Backend Domain Search (.NET 10)**:
   - Search `<codebase_path>` for occurrences of `$ARGUMENTS` inside all `.cs` and `.csproj` files to locate entity models, DI registrations, services and API route controllers.
   - Match API routes found here to the UI client calls from step 1, so a change on one side shows every consumer on the other.
3. **Internal Wiki Synthesis**:
   - Cross-reference `wiki/` for strategy documents or architectural plan notes mapping to this entity, including Log Event IDs in `wiki/UltronLogEventMap.md`.
4. **Compile Boundary Blast Matrix**:
   - A scannable table: `File | Layer (UI/API) | Relationship | Blast Radius (High/Med/Low)`, categorized by dependency complexity.
   - List affected files with no test coverage.
   - Offer to draft an intent proposal from `system/templates/intent-shaper.md` with the **Downstream Impact & Risk Radii** section filled in.

Begin analyzing boundary impacts for: $ARGUMENTS
