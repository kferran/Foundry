#!/usr/bin/env bats
# The factory line's conformance checks (factory F0 spec §3.8). The pipeline test: a spec or plan dated on or
# after PIPELINE_SINCE carries the header lines FOUNDRY.md Development requires; older documents are
# grandfathered by the date their file name starts with, so the test needs no allowlist.

setup() {
  VAULT_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  cd "$VAULT_ROOT"
}

PIPELINE_SINCE=2026-10-21

# pipeline_problems <root>: one `<path>: <problem>` line for each required line missing from <root>'s specs
# (docs/superpowers/specs/*-design.md) and plans (docs/superpowers/plans/*.md) dated PIPELINE_SINCE or later.
# CI does not call gh, so a Grill line is checked by pattern: an issue URL, a `## Grill` section, or
# `not an owner idea: <source>`.
pipeline_problems() {
  local f rel name line spec
  shopt -s nullglob
  for f in "$1"/docs/superpowers/specs/*-design.md "$1"/docs/superpowers/plans/*.md; do
    rel="${f#"$1"/}"
    name="${f##*/}"
    [[ "${name:0:10}" < "$PIPELINE_SINCE" ]] && continue
    case "$rel" in
      docs/superpowers/specs/*)
        line="$(grep -m 1 '^\*\*Grill:\*\*' "$f" || true)"
        if [[ -z "$line" ]]; then
          echo "$rel: no **Grill:** line"
        elif ! grep -qE 'https://github\.com/[^/ ]+/[^/ ]+/issues/[0-9]+|## Grill|not an owner idea: ' <<< "$line"; then
          echo "$rel: the **Grill:** line names no issue URL, \`## Grill\` section or \`not an owner idea:\` source"
        fi
        grep -q '^\*\*Builder check:\*\*' "$f" || echo "$rel: no **Builder check:** line"
        grep -qE '^\*\*Blueprint:\*\* (Source|Poller|Compile run|Work Order|none: )' "$f" \
          || echo "$rel: no **Blueprint:** line naming Source, Poller, Compile run, Work Order or none: <why>"
        ;;
      *)
        grep -qF 'REQUIRED SUB-SKILL' "$f" || echo "$rel: no writing-plans header (REQUIRED SUB-SKILL)"
        grep -qx '## Global Constraints' "$f" || echo "$rel: no ## Global Constraints section"
        grep -qx '## Review Focus' "$f" || echo "$rel: no ## Review Focus section"
        line="$(grep -m 1 '^\*\*Spec:\*\*' "$f" || true)"
        spec="$(grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}-[A-Za-z0-9.-]+-design\.md' <<< "$line" | head -n 1 || true)"
        if [[ -z "$line" ]]; then
          echo "$rel: no **Spec:** line"
        elif [[ -z "$spec" || ! -f "$1/docs/superpowers/specs/$spec" ]]; then
          echo "$rel: the **Spec:** line names no spec file that exists"
        fi
        ;;
    esac
  done
}

@test "every spec and plan dated $PIPELINE_SINCE or later carries the pipeline's header lines (factory F0 §3.8)" {
  run pipeline_problems "$VAULT_ROOT"
  printf '%s\n' "$output"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "the pipeline test fails a new spec or plan missing a line, and passes an older one and a complete one (factory F0 §3.8)" {
  r="$BATS_TEST_TMPDIR/repo"
  s="$r/docs/superpowers/specs"
  p="$r/docs/superpowers/plans"
  mkdir -p "$s" "$p"
  head='> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.\n\n'
  printf '# Old\n\nNo header lines; grandfathered by its date.\n' > "$s/2026-10-01-old-design.md"
  printf '# Old plan\n' > "$p/2026-10-01-old.md"
  printf '# Bad\n\n**Builder check:** 2026-10-21, none.\n**Blueprint:** Source\n' > "$s/2026-10-21-bad-design.md"
  printf '# Good\n\n**Grill:** 2026-10-21, https://github.com/o/r/issues/7\n**Builder check:** 2026-10-21, two questions, both settled.\n**Blueprint:** none: docs only.\n' \
    > "$s/2026-10-21-good-design.md"
  printf '# Weak\n\n**Grill:** 2026-10-22, talked it over\n**Builder check:** 2026-10-22, none.\n**Blueprint:** Compile run\n' \
    > "$s/2026-10-22-weak-grill-design.md"
  printf "# Bad plan\n\n$head**Spec:** \`docs/superpowers/specs/2026-10-21-good-design.md\`\n\n## Global Constraints\n" > "$p/2026-10-21-bad.md"
  printf "# Good plan\n\n$head**Spec:** \`docs/superpowers/specs/2026-10-21-good-design.md\`\n\n## Global Constraints\n\n## Review Focus\n" \
    > "$p/2026-10-21-good.md"
  printf "# Lost plan\n\n$head**Spec:** \`docs/superpowers/specs/2026-10-21-gone-design.md\`\n\n## Global Constraints\n\n## Review Focus\n" \
    > "$p/2026-10-21-lost.md"
  run pipeline_problems "$r"
  [ "$status" -eq 0 ]
  [ "$output" = "$(printf '%s\n' \
    'docs/superpowers/specs/2026-10-21-bad-design.md: no **Grill:** line' \
    'docs/superpowers/specs/2026-10-22-weak-grill-design.md: the **Grill:** line names no issue URL, `## Grill` section or `not an owner idea:` source' \
    'docs/superpowers/plans/2026-10-21-bad.md: no ## Review Focus section' \
    'docs/superpowers/plans/2026-10-21-lost.md: the **Spec:** line names no spec file that exists')" ]
}
