#!/usr/bin/env bats
# The factory line's conformance checks (factory F0 spec §3.5, §3.6, §3.8; F3 spec §3.2). The part homes are rules:
# each line of PART_HOMES is a design fact, and a new line needs the owner's review with its reason. The timing
# overrun list still only shrinks (#299). The pipeline test: a spec or plan dated on or
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

# --- The part homes (factory F0 spec §3.5, F3 spec §3.2) ---

# One line per home or other shape: "<kind> <path>[:<name>]  # <reason>". Each line is a design fact, not a debt: a new
# line needs the owner's review with its reason.
PART_HOMES='
walker system/scripts/vaultlib/nightshift_session.py  # other shape: a Work Order session with many tools and no single connector (F1 spec)
walker system/scripts/vaultlib/connector.py  # home: the shared walker (F1 spec §3.1)
helper system/scripts/lib_fetch.sh:logline  # home: the shared fetch helpers (F1 spec §3.2)
helper system/scripts/lib_fetch.sh:alert_once  # home: the shared fetch helpers (F1 spec §3.2)
helper system/scripts/lib_fetch.sh:fail  # home: the shared fetch helpers (F1 spec §3.2)
helper system/scripts/lib_fetch.sh:skip  # home: the shared fetch helpers (F1 spec §3.2)
helper system/scripts/vault_sync.sh:fail  # other shape: fail <step> <reason> for a sync step, no fetch exit
fail-class system/scripts/vaultlib/connector.py  # home: the one Fail every retrofitted module imports (F1 spec §3.1)
config system/scripts/vaultlib/config.py  # home: the one config reader (F3 spec §3.3)
config system/scripts/vaultlib/extensions.py  # home: enable edits the extensions: line as text (F3 spec §3.2)
stub system/tests/stub_claude  # other shape: the headless stub (STUB_MODE), not a connector stub
stub system/tests/stub_claude_nightshift  # other shape: the Work Order stub, not a connector stub
stub system/tests/stub_claude_connector  # home: the one connector stub (F1 spec §3.4)
'

# copies <root>: every copy of a shared part in <root>'s tracked tree, one "<kind> <path>[:<name>]" line each, sorted.
copies() {
  local -a src=(-- 'system/scripts/*' 'extensions/*/scripts/*') py=(-- 'system/scripts/*.py' 'extensions/*/scripts/*.py')
  {
    # Stream walkers: a file that reads tool results itself (file level: a docstring naming tool_use_id counts too).
    git -C "$1" grep -lE "[\"']tool_result[\"']|tool_use_id" "${py[@]}" | sed 's/^/walker /'
    # Shell helpers defined at top level.
    git -C "$1" grep -nE '^(function +)?(logline|alert_once|fail|skip)( *\(\)| *\{)' "${src[@]}" \
      | sed -E 's/^([^:]+):[0-9]+:(function +)?([a-z_]+).*/helper \1:\3/'
    git -C "$1" grep -lE '^class Fail\b' "${py[@]}" | sed 's/^/fail-class /'
    # Config readers: any script that names config.md as a path literal.
    git -C "$1" grep -lE "config\.md[\"']" "${py[@]}" | sed 's/^/config /'
    # Test doubles: claude stubs and pytest modules with their own stream() builder (helpers.py is F1's shared home).
    git -C "$1" ls-files | grep -E '(^|/)stub_claude[^/]*$' | sed 's/^/stub /'
    git -C "$1" grep -lE '^def stream\(' -- 'system/tests/python/*.py' 'extensions/*/tests/python/*.py' ':!system/tests/python/helpers.py' | sed 's/^/stream-builder /'
  } | sort -u
}

# new_copies <root>: the copies in <root> that PART_HOMES does not list.
new_copies() {
  comm -13 <(sed -E 's/ +#.*$//; /^$/d' <<< "$PART_HOMES" | sort -u) <(copies "$1")
}

@test "no new copy of a shared part (factory F0 spec §3.5)" {
  allowed="$(sed -E 's/ +#.*$//; /^$/d' <<< "$PART_HOMES" | sort -u)"
  found="$(copies "$VAULT_ROOT")"
  # A copy not on the list: use the shared part, or add the line with its reason in a PR the owner reviews.
  run new_copies "$VAULT_ROOT"
  [ "$status" -eq 0 ]
  echo "new copies: $output"
  [ -z "$output" ]
  # A listed home that is gone: delete its line in the same PR.
  run comm -23 <(printf '%s\n' "$allowed") <(printf '%s\n' "$found")
  echo "listed copies no longer found: $output"
  [ -z "$output" ]
}

@test "a new copy of a shared part fails, a home passes (factory F3 §3.2)" {
  r="$BATS_TEST_TMPDIR/repo"
  mkdir -p "$r"
  git ls-files -z | xargs -0 cp --parents -t "$r"
  git -C "$r" init -q
  mkdir -p "$r/extensions/handoffs/scripts"
  printf '%s\n' 'for b in blocks:' '    if b.get("type") == "tool_result":' '        pass' > "$r/system/scripts/vaultlib/walker2.py"
  printf '%s\n' 'p = root / "system" / "config.md"' > "$r/extensions/handoffs/scripts/cfg.py"
  git -C "$r" add -A
  run new_copies "$r"
  printf '%s\n' "$output"
  [ "$status" -eq 0 ]
  [ "$output" = "$(printf '%s\n' 'config extensions/handoffs/scripts/cfg.py' 'walker system/scripts/vaultlib/walker2.py')" ]
}

# --- The timing rule (factory F0 spec §3.6, defect class C3; F3 spec §3.4) ---
# The tables hold core only. An extension states its budget in its manifest (`budget:` values, steps and out), which
# timing_manifests.py turns into the same keys and steps: a value becomes <ext>.<NAME>, the extension's tick unit
# tick/<ext>, and each tick and smoke row adds its own value and step.
# VALUES: "<key> <file> <ERE>". The ERE must match exactly one line of the file; its first group is the value, in seconds
# or with a unit (s, m, min, h). Changing a default the table names, or the line around it, fails here until the table
# follows; the sums below then decide whether it still fits.
TIMING_VALUES='
grace.connector system/scripts/lib_connector.sh timeout -k ([0-9]+) "\$CONNECTOR_TIMEOUT"
grace.headless system/scripts/run_headless.sh timeout -k ([0-9]+s) "\$TIMEOUT"
grace.listing system/scripts/lib_confine.sh timeout -k ([0-9]+) [0-9]+ "\$\{CLAUDE_BIN
listing system/scripts/lib_confine.sh timeout -k [0-9]+ ([0-9]+) "\$\{CLAUDE_BIN
headless system/scripts/run_headless.sh \{HEADLESS_TIMEOUT:-([0-9]+m)\}
headless.lock system/scripts/run_headless.sh \{HEADLESS_LOCK_WAIT:-([0-9]+)\}
calendar system/scripts/calendar_fetch.sh \{CALENDAR_TIMEOUT:-([0-9]+)\}
now.seed system/scripts/brief_prep.sh NOW_LOCK_WAIT="\$\{ARCHIVE_LOCK_WAIT:-([0-9]+)\}" system/scripts/now\.py seed
now.archive.work system/scripts/brief_prep.sh NOW_LOCK_WAIT="\$\{ARCHIVE_LOCK_WAIT:-([0-9]+)\}" system/scripts/now\.py archive --partition work
now.archive.personal system/scripts/brief_prep.sh NOW_LOCK_WAIT="\$\{ARCHIVE_LOCK_WAIT:-([0-9]+)\}" system/scripts/now\.py archive --partition personal
archive.lock system/scripts/brief_prep.sh flock -w "\$\{ARCHIVE_LOCK_WAIT:-([0-9]+)\}"
gh system/scripts/debrief_prep.sh \{GH_TIMEOUT:-([0-9]+)\}
intake.lock system/scripts/vaultlib/intake.py self\.lock\("run\.lock", timeout=([1-9][0-9]*)\)
intake.runs system/scripts/vaultlib/intake.py "INTAKE_MAX_RUNS", "([0-9]+)"
meetings system/scripts/meetings_fetch.sh \{MEETINGS_TIMEOUT:-([0-9]+)\}
meetings.reads system/scripts/meetings_fetch.sh ^MAX_READS=([0-9]+)$
notify system/scripts/notify.sh \{NOTIFY_TIMEOUT:-([0-9]+)\}
sync system/scripts/vault_sync.sh \{SYNC_DEADLINE:-([0-9]+)\}
triage.mail system/scripts/triage_fetch.sh \{TRIAGE_TIMEOUT:-([0-9]+)\}
triage.chat system/scripts/triage_fetch.sh \{TRIAGE_CHAT_TIMEOUT:-([0-9]+)\}
triage.lock system/scripts/triage.py intake\.lock\("run\.lock", timeout=([0-9]+)\)
update.lock system/scripts/update_template.sh \{UPDATE_LOCK_WAIT:-([0-9]+)\}
update.fetch system/scripts/update_template.sh \{UPDATE_FETCH_TIMEOUT:-([0-9]+)\}
smoke.version system/scripts/smoke_check.sh \{SMOKE_VERSION_TIMEOUT:-([0-9]+)\}
smoke.extensions system/scripts/smoke_check.sh timeout ([0-9]+) system/scripts/extensions\.py smoke
smoke.units system/scripts/smoke_check.sh \{SMOKE_UNITS_TIMEOUT:-([0-9]+)\}
row.calendar system/scripts/smoke_check.sh \{SMOKE_CALENDAR_TIMEOUT:-([0-9]+)\}
row.meetings system/scripts/smoke_check.sh \{SMOKE_MEETINGS_TIMEOUT:-([0-9]+)\}
row.triage system/scripts/smoke_check.sh \{SMOKE_TRIAGE_TIMEOUT:-([0-9]+)\}" system/scripts/triage_fetch\.sh --check --source mail
row.triage_chat system/scripts/smoke_check.sh \{SMOKE_TRIAGE_TIMEOUT:-([0-9]+)\}" system/scripts/triage_fetch\.sh --check --source chat
'

# STEPS: "<unit> <count> <grace> <value>": one run of <unit> can wait <count> x (<value> + <grace>). A unit is a template
# unit (its limit is TimeoutStartSec in its .service.in), "smoke/<row>" (its limit is row.<row>: the row's --check) or
# "tick/<ext>" (its limit is tick.<ext>: the extension's tick timeout).
# <count> is a number or a VALUES key (the script's own cap); <grace> is a grace.* key, or - when the step has no kill
# grace. Every claude process counts, the server listing (`claude mcp list`, once per process and again after each
# `unset CONFINE_SETTINGS`) included, and so do sessions a script runs through another script.
# Out of the table: the Work Order unit (foundry-nightshift: per-order sessions under its 14 h limit, budgeted in Python
# by the runner). Unbounded waits no sum can hold: ingest's run.lock (`flock 9` with no -w in
# run_headless.sh), tracked with intake's overrun in #299. The server drop-ins (install_units.sh DROPIN_TIMEOUT) add
# 15 min to intake, brief, debrief and update for vault_sync.sh's two sync deadlines; the table holds the templates.
TIMING_STEPS='
brief 1 grace.listing listing  # brief_prep.sh: calendar_fetch.sh, its own process
brief 1 grace.connector calendar
brief 1 - now.seed
brief 1 - now.archive.work
brief 1 - now.archive.personal
brief 1 - archive.lock
brief 1 - headless.lock  # run_headless.sh brief
brief 1 grace.headless headless
debrief 3 - gh  # debrief_prep.sh: three gh searches
debrief 1 - headless.lock
debrief 1 grace.headless headless
intake 1 - intake.lock  # the briefing Notes extract waits for run.lock
intake intake.runs grace.headless headless  # inbox files and digest batches, at most INTAKE_MAX_RUNS a tick
meetings 1 grace.listing listing
meetings 1 grace.connector meetings  # the search
meetings meetings.reads grace.connector meetings  # one read session per Doc, at most MAX_READS
notify 1 grace.listing listing
notify 2 grace.connector notify  # the day thread parent post (slack_notify_thread daily), then the notice
smoke 1 - smoke.version
smoke 1 - row.calendar
smoke 1 - row.meetings
smoke 1 - row.triage
smoke 1 - row.triage_chat
smoke 1 - smoke.extensions
smoke 1 - smoke.units
sync 1 - sync  # one deadline across every git call of the sync
triage 2 grace.listing listing  # each source (mail, chat) runs in its own process
triage 1 grace.connector triage.mail
triage 1 grace.connector triage.chat
triage 2 - triage.lock  # triage.py record, once per source
update 1 - update.lock
update 1 - update.fetch
smoke/calendar 1 grace.listing listing
smoke/calendar 1 grace.connector calendar
smoke/meetings 1 grace.listing listing  # --check runs the search only
smoke/meetings 1 grace.connector meetings
smoke/triage 1 grace.listing listing
smoke/triage 1 grace.connector triage.mail
smoke/triage_chat 1 grace.listing listing
smoke/triage_chat 1 grace.connector triage.chat
'

# Units over their limit today: "<unit> <issue>  # by how much". The list may only shrink: a unit that fits fails until
# its line goes.
TIMING_OVERRUNS='
intake #299  # 7,270 s against 90 min, and ingest run.lock wait is unbounded
smoke #299  # 3,000 s against 35 min with one telemetry source, 120 s more per further source
watch #299  # 1,815 s against 29 min: the five server listings are not in watch_fetch.sh budget comment
smoke/calendar #299  # 235 s against 210: the server listing
smoke/watch #299  # 1,225 s against 1,140: three server listings
'
TIMING_OUT='foundry-nightshift'  # an extension's unit with no session says so in its manifest's budget.out

secs() {  # <n>[s|m|min|h] -> seconds
  case "$1" in
    *min) echo $(( ${1%min} * 60 )) ;;
    *h) echo $(( ${1%h} * 3600 )) ;;
    *m) echo $(( ${1%m} * 60 )) ;;
    *s) echo "${1%s}" ;;
    *) echo "$1" ;;
  esac
}

# read_value <file> <ERE>: the first group of the one line of <file> that matches, in seconds; fails otherwise.
read_value() {
  local line
  line="$(grep -E -- "$2" "$1")" || { echo "no line of $1 matches: $2" >&2; return 1; }
  [[ "$line" != *$'\n'* ]] || { echo "more than one line of $1 matches: $2" >&2; return 1; }
  [[ "$line" =~ $2 ]] || { echo "bash cannot read: $2" >&2; return 1; }
  secs "${BASH_REMATCH[1]}"
}

unit_file() {  # <unit>: its template, core or extension
  local f
  for f in "system/systemd/foundry-$1.service.in" extensions/*/units/"foundry-$1.service.in"; do
    [[ ! -f "$f" ]] || { echo "$f"; return 0; }
  done
  return 1
}

# timing_problems <root>: the timing rule on <root>'s tree, the core tables plus its manifests' budgets. Prints one
# "# <unit>: <total> s of <limit> s" line per summed unit and one line per problem.
timing_problems() (
  cd "$1" || exit 1
  declare -A val total
  local key file re unit count grace v n g limit kind rest man steps="$TIMING_STEPS" out=" $TIMING_OUT " used=" "
  man="$(python3 "$VAULT_ROOT/system/tests/timing_manifests.py" . 2>&1)" || echo "timing_manifests.py failed: $man"
  while read -r kind rest; do
    case "$kind" in
      V) val[${rest%% *}]="${rest#* }" ;;
      S) steps+="$rest"$'\n' ;;
      O) out+="foundry-$rest " ;;
      P) echo "$rest" ;;
    esac
  done <<< "$man"
  while read -r key file re; do
    [[ -n "$key" ]] || continue
    [[ "$file" != extensions/* ]] || echo "$key: names $file; an extension's budget belongs in its manifest"
    if v="$(read_value "$file" "$re" 2>&1)"; then val[$key]="$v"; else echo "$key: $v"; fi
  done <<< "$TIMING_VALUES"
  while read -r unit count grace key _; do
    [[ -n "$unit" ]] || continue
    used+="$count $grace $key "
    n="$count"; [[ "$n" =~ ^[0-9]+$ ]] || n="${val[$count]:-x}"
    g=0; [[ "$grace" == - ]] || g="${val[$grace]:-x}"
    v="${val[$key]:-x}"
    if [[ "$n$g$v" == *x* ]]; then echo "$unit: a step names an unknown key ($count $grace $key)"; continue; fi
    total[$unit]=$(( ${total[$unit]:-0} + n * (v + g) ))
  done <<< "$steps"
  # Every template unit is summed or out with its reason (above, or its manifest's budget.out), and every known
  # overrun names a unit the table sums.
  for file in system/systemd/*.service.in extensions/*/units/*.service.in; do
    unit="${file##*/foundry-}" unit="${unit%.service.in}"
    [[ -n "${total[$unit]:-}" || "$out" == *" foundry-$unit "* ]] || echo "$unit: no steps in the table"
  done
  while read -r unit _; do
    [[ -z "$unit" || -n "${total[$unit]:-}" ]] || echo "$unit: a known overrun with no steps in the table"
  done <<< "$TIMING_OVERRUNS"
  # Every session default has its value (a VALUES line, or its manifest's budget.values) and a step that sums it, and
  # every core smoke row its row.<row> line, so a new session cannot go unsummed (F3 §3.1 rule 5).
  while IFS=: read -r file var; do
    if [[ "$file" == extensions/* ]]; then
      key="${file#extensions/}" key="${key%%/*}.$var"
      [[ -n "${val[$key]:-}" ]] || { echo "$file: $var has no budget value in its manifest"; continue; }
    else
      key="$(awk -v f="$file" -v v="{$var:-" '$2 == f && index($0, v) { print $1; exit }' <<< "$TIMING_VALUES")"
      [[ -n "$key" ]] || { echo "$file: $var has no VALUES line"; continue; }
    fi
    [[ "$used" == *" $key "* ]] || echo "$file: $var has no step"
  done < <(git grep -oE 'CONNECTOR_TIMEOUT="\$\{[A-Z_]+|\{HEADLESS_TIMEOUT' -- 'system/scripts/*' 'extensions/*/scripts/*' \
             | sed -E 's/:.*[{]/:/')
  while read -r key; do
    [[ -n "${val[row.$key]:-}" ]] || echo "smoke row $key: no row.$key VALUES line"
  done < <(sed -nE 's/^ *connector ([a-z_]+) .*/\1/p' system/scripts/smoke_check.sh)
  for unit in "${!total[@]}"; do
    case "$unit" in
      smoke/*) limit="${val[row.${unit#smoke/}]:-}" ;;
      tick/*) limit="${val[tick.${unit#tick/}]:-}" ;;
      *) file="$(unit_file "$unit")" || { echo "$unit: no unit template"; continue; }
         limit="$(read_value "$file" '^TimeoutStartSec=([0-9]+(s|min|h)?)$')" || { echo "$unit: no TimeoutStartSec"; continue; } ;;
    esac
    [[ -n "$limit" ]] || { echo "$unit: no limit"; continue; }
    echo "# $unit: ${total[$unit]} s of $limit s"
    if grep -qE "^$unit " <<< "$TIMING_OVERRUNS"; then
      (( total[$unit] > limit )) || echo "$unit: fits now (${total[$unit]} s of $limit s); delete its known-overrun line"
    elif (( total[$unit] > limit )); then
      echo "$unit: ${total[$unit]} s of waits against a $limit s limit"
    fi
  done
)

@test "every unit's sessions fit its time limit (factory F0 spec §3.6, F3 §3.4)" {
  run timing_problems "$VAULT_ROOT"
  printf '%s\n' "$output"
  [ "$status" -eq 0 ]
  [ -z "$(grep -v '^# ' <<< "$output")" ]
}

@test "a manifest budget that disagrees, a session no step sums, a tick over its timeout and a manifest that does not load each fail (factory F3 §3.4)" {
  r="$BATS_TEST_TMPDIR/repo"
  mkdir -p "$r"
  git ls-files -z | xargs -0 cp --parents -t "$r"
  git -C "$r" init -q
  sed -i 's/WATCH_SLACK_TIMEOUT: 420/WATCH_SLACK_TIMEOUT: 421/' "$r/extensions/intraday/extension.md"
  sed -i '/grace\.connector JIRA_TIMEOUT/d' "$r/extensions/handoffs/extension.md"
  sed -i 's/timeout: 1900/timeout: 1000/' "$r/extensions/telemetry/extension.md"
  mkdir -p "$r/extensions/demo"
  printf '%s\n' '---' 'name: demo' 'contract: 1' 'bogus: 1' '---' > "$r/extensions/demo/extension.md"
  printf '%s\n' 'CONNECTOR_TIMEOUT="${EXTRA_TIMEOUT:-60}"' > "$r/extensions/handoffs/scripts/extra.sh"
  git -C "$r" add -A
  run timing_problems "$r"
  printf '%s\n' "$output"
  [ "$status" -eq 0 ]
  [ "$(grep -v '^# ' <<< "$output" | LC_ALL=C sort)" = "$(printf '%s\n' \
    'demo: unknown manifest field(s) bogus' \
    'extensions/handoffs/scripts/extra.sh: EXTRA_TIMEOUT has no budget value in its manifest' \
    'extensions/handoffs/scripts/jira_fetch.sh: JIRA_TIMEOUT has no step' \
    'intraday: budget value WATCH_SLACK_TIMEOUT is 421; extensions/intraday/scripts/watch_fetch.sh says 420' \
    'tick/telemetry: 1395 s of waits against a 1000 s limit')" ]
}
