# Health (health scorecard spec §3.4): score the week and write the brief's lines. Sourced by brief_prep.sh in a
# subshell, from the vault root, with PREP_DATE, PREP_DIR and the prep_* functions (extensions spec §3). Writes
# sections/health.md: the whole scorecard on a Monday, only the breached metrics on other days, empty when none.
: > "$PREP_DIR/sections/health.md"
rc=0
prep_write sections/health.md extensions/health/scripts/health.py score "$PREP_DATE" || rc=$?
(( rc == 0 )) || prep_unavailable "health: health.py score failed (exit $rc; see $PREP_DIR/prep_errors.log)"
exit 0
