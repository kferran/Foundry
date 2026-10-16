# New DTCC changes since the latest earlier briefing (DTCC watcher spec §7). Sourced by brief_prep.sh in a subshell,
# from the vault root, with PREP_DATE, PREP_DIR and the prep_* functions (extensions spec §3). Empty without a map.
: > "$PREP_DIR/sections/dtcc.md"
if [[ ! -f system/dtcc/map.yaml ]]; then
  prep_source dtcc off
  exit 0
fi
rc=0
prep_write sections/dtcc.md extensions/dtcc/scripts/dtcc_watch.py --brief "$PREP_DATE" || rc=$?
if (( rc == 0 )); then prep_source dtcc ok; else prep_source dtcc failed "dtcc_watch.py --brief exit $rc"; fi
(( rc == 0 )) || prep_unavailable "dtcc: dtcc_watch.py --brief failed (see $PREP_DIR/prep_errors.log)"
exit 0
