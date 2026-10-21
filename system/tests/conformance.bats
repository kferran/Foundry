#!/usr/bin/env bats
# The factory line's conformance checks (factory F0 spec §3.8). The pipeline test: a spec or plan dated on or
# after PIPELINE_SINCE carries the header lines FOUNDRY.md Development requires; older documents are
# grandfathered by the date their file name starts with, so the test needs no allowlist.

setup() {
  VAULT_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  cd "$VAULT_ROOT"
  # A vault's own extensions and docs are the owner's, and /backup runs the suites there.
  [ ! -e system/config.md ] || skip "this checkout is a vault (system/config.md exists); the rule guards the template"
}

PIPELINE_SINCE=2026-10-21

# grill_problem <root> <spec> <rel>: why the spec's Grill line fails, or nothing. CI does not call gh, so the line
# is checked by pattern: `not an owner idea: <source>` with a real source, an issue URL, or a `## Grill` section
# that the spec itself or the file its **Program:** line names holds.
grill_problem() {
  local line src prog
  line="$(grep -m 1 '^\*\*Grill:\*\*' "$2" || true)"
  if [[ -z "$line" ]]; then
    echo "$3: no **Grill:** line"
  elif [[ "$line" == *'not an owner idea:'* ]]; then
    src="${line#*not an owner idea:}"
    src="${src#"${src%%[! ]*}"}"
    [[ -n "$src" && "$src" != '<'* ]] || echo "$3: the **Grill:** line's \`not an owner idea:\` names no source"
  elif grep -qE 'https://github\.com/[^/ ]+/[^/ ]+/issues/[0-9]+' <<< "$line"; then
    :
  elif [[ "$line" == *'## Grill'* ]]; then
    prog="$(grep -m 1 '^\*\*Program:\*\*' "$2" | grep -oE 'docs/[^` )]+\.md' | head -n 1 || true)"
    grep -qx '## Grill' "$2" || { [[ -n "$prog" && -f "$1/$prog" ]] && grep -qx '## Grill' "$1/$prog"; } \
      || echo "$3: the **Grill:** line cites a \`## Grill\` section that neither the spec nor its **Program:** file has"
  else
    echo "$3: the **Grill:** line names no issue URL, \`## Grill\` section or \`not an owner idea:\` source"
  fi
}

# pipeline_problems <root>: one `<path>: <problem>` line for each required line missing from <root>'s specs
# (docs/superpowers/specs/*.md, research briefs excepted) and plans (docs/superpowers/plans/**/*.md) dated
# PIPELINE_SINCE or later. A file whose name starts with no date is checked.
pipeline_problems() {
  local f rel name line spec
  while IFS= read -r f; do
    rel="${f#"$1"/}"
    name="${f##*/}"
    if [[ "${name:0:10}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ && "${name:0:10}" < "$PIPELINE_SINCE" ]]; then continue; fi
    case "$rel" in
      docs/superpowers/specs/*)
        grill_problem "$1" "$f" "$rel"
        grep -qE '^\*\*Builder check:\*\* *[^ <]' "$f" || echo "$rel: no **Builder check:** line with its outcome"
        grep -qE '^\*\*Blueprint:\*\* ((Source|Poller|Compile run|Work Order)( |$|[,.])|none: *[^ <])' "$f" \
          || echo "$rel: no **Blueprint:** line naming Source, Poller, Compile run, Work Order or none: <why>"
        ;;
      *)
        grep -qF 'REQUIRED SUB-SKILL' "$f" || echo "$rel: no writing-plans header (REQUIRED SUB-SKILL)"
        grep -qx '## Global Constraints' "$f" || echo "$rel: no ## Global Constraints section"
        grep -qx '## Review Focus' "$f" || echo "$rel: no ## Review Focus section"
        line="$(grep -m 1 '^\*\*Spec:\*\*' "$f" || true)"
        spec="$(grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}-[A-Za-z0-9._-]+\.md' <<< "$line" | head -n 1 || true)"
        if [[ -z "$line" ]]; then
          echo "$rel: no **Spec:** line"
        elif [[ -z "$spec" || ! -f "$1/docs/superpowers/specs/$spec" ]]; then
          echo "$rel: the **Spec:** line names no spec file that exists"
        fi
        ;;
    esac
  done < <({ find "$1/docs/superpowers/specs" -maxdepth 1 -type f -name '*.md' ! -name '*-research-brief.md'
             find "$1/docs/superpowers/plans" -type f -name '*.md'; } 2>/dev/null | LC_ALL=C sort)
}

@test "every spec and plan dated $PIPELINE_SINCE or later carries the pipeline's header lines (factory F0 §3.8)" {
  run pipeline_problems "$VAULT_ROOT"
  printf '%s\n' "$output"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# doc <path> <line>…: write a fixture document with a title and the given lines.
doc() { local f="$1"; shift; mkdir -p "${f%/*}"; printf '%s\n' '# T' '' "$@" > "$f"; }

@test "the pipeline test fails each missing or placeholder line in a new spec or plan, and passes old and complete ones (factory F0 §3.8)" {
  r="$BATS_TEST_TMPDIR/repo"
  s="$r/docs/superpowers/specs"
  p="$r/docs/superpowers/plans"
  hdr='> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.'
  ok_b='**Builder check:** 2026-10-21, two questions, both settled.'
  cites='**Grill:** 2026-10-21, recorded in the program plan'"'"'s `## Grill` section.'
  # Passing: grandfathered by date, a research brief, and complete documents.
  doc "$s/2026-10-01-old-design.md"
  doc "$s/2026-10-21-x-research-brief.md"
  doc "$p/2026-10-01-old.md"
  doc "$s/2026-10-21-good-design.md" '**Grill:** 2026-10-21, https://github.com/o/r/issues/7' "$ok_b" '**Blueprint:** none: docs only.'
  doc "$r/docs/superpowers/prog.md" '## Grill' 'Decided.'
  doc "$s/2026-10-21-program-design.md" '**Program:** `docs/superpowers/prog.md`' "$cites" "$ok_b" '**Blueprint:** Source (its parts)'
  doc "$s/2026-10-21-own-grill-design.md" '**Grill:** 2026-10-21, see `## Grill` below.' "$ok_b" '**Blueprint:** Work Order' '## Grill' 'Decided.'
  doc "$p/2026-10-21-good.md" "$hdr" '**Spec:** `docs/superpowers/specs/2026-10-21-good-design.md`' '## Global Constraints' '## Review Focus'
  # Failing.
  doc "$s/2026-10-21-no-grill-section-design.md" "$cites" "$ok_b" '**Blueprint:** Poller'
  doc "$s/2026-10-21-lost-program-design.md" '**Program:** `docs/superpowers/gone.md`' "$cites" "$ok_b" '**Blueprint:** Compile run.'
  doc "$s/2026-10-21-placeholder-design.md" '**Grill:** not an owner idea: <source>' '**Builder check:**' '**Blueprint:** none:'
  doc "$s/2026-10-21-empty-source-design.md" '**Grill:** not an owner idea:' "$ok_b" '**Blueprint:** Sourcery'
  doc "$s/2026-10-22-weak-grill-design.md" '**Grill:** 2026-10-22, talked it over' "$ok_b" '**Blueprint:** Compile run'
  doc "$s/2026-10-23-empty.md"
  doc "$p/2026-10-21-bad.md" "$hdr" '**Spec:** `docs/superpowers/specs/2026-10-21-good-design.md`' '## Global Constraints'
  doc "$p/2026-10-21-lost.md" "$hdr" '**Spec:** `docs/superpowers/specs/2026-10-21-gone-design.md`' '## Global Constraints' '## Review Focus'
  doc "$p/sub/2026-10-21-nested.md" "$hdr" '**Spec:** `docs/superpowers/specs/2026-10-21-good-design.md`' '## Review Focus'
  doc "$p/2026-10-23-empty.md"
  run pipeline_problems "$r"
  printf '%s\n' "$output"
  [ "$status" -eq 0 ]
  P=docs/superpowers/plans S=docs/superpowers/specs
  [ "$output" = "$(printf '%s\n' \
    "$P/2026-10-21-bad.md: no ## Review Focus section" \
    "$P/2026-10-21-lost.md: the **Spec:** line names no spec file that exists" \
    "$P/2026-10-23-empty.md: no writing-plans header (REQUIRED SUB-SKILL)" \
    "$P/2026-10-23-empty.md: no ## Global Constraints section" \
    "$P/2026-10-23-empty.md: no ## Review Focus section" \
    "$P/2026-10-23-empty.md: no **Spec:** line" \
    "$P/sub/2026-10-21-nested.md: no ## Global Constraints section" \
    "$S/2026-10-21-empty-source-design.md: the **Grill:** line's \`not an owner idea:\` names no source" \
    "$S/2026-10-21-empty-source-design.md: no **Blueprint:** line naming Source, Poller, Compile run, Work Order or none: <why>" \
    "$S/2026-10-21-lost-program-design.md: the **Grill:** line cites a \`## Grill\` section that neither the spec nor its **Program:** file has" \
    "$S/2026-10-21-no-grill-section-design.md: the **Grill:** line cites a \`## Grill\` section that neither the spec nor its **Program:** file has" \
    "$S/2026-10-21-placeholder-design.md: the **Grill:** line's \`not an owner idea:\` names no source" \
    "$S/2026-10-21-placeholder-design.md: no **Builder check:** line with its outcome" \
    "$S/2026-10-21-placeholder-design.md: no **Blueprint:** line naming Source, Poller, Compile run, Work Order or none: <why>" \
    "$S/2026-10-22-weak-grill-design.md: the **Grill:** line names no issue URL, \`## Grill\` section or \`not an owner idea:\` source" \
    "$S/2026-10-23-empty.md: no **Grill:** line" \
    "$S/2026-10-23-empty.md: no **Builder check:** line with its outcome" \
    "$S/2026-10-23-empty.md: no **Blueprint:** line naming Source, Poller, Compile run, Work Order or none: <why>")" ]
}
