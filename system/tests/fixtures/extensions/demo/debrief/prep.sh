# Fixture debrief prep: sourced by debrief_prep.sh in a subshell with PREP_DATE, PREP_DIR, SECTIONS and the prep_*
# functions. DEMO_PREP_FAIL=1 makes it fail.
[[ "${DEMO_PREP_FAIL:-}" != 1 ]] || { echo "demo debrief prep: boom" >&2; exit 3; }
printf '%s\n' "- demo evening line" > "$SECTIONS/demo.md"
