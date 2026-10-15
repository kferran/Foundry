# Fixture brief prep: sourced by brief_prep.sh in a subshell with PREP_DATE, PREP_DIR and the prep_* functions.
# DEMO_PREP_FAIL=1 makes it fail, for the test that a broken extension costs one unavailable line.
[[ "${DEMO_PREP_FAIL:-}" != 1 ]] || { echo "demo prep: boom" >&2; exit 3; }
prep_write sections/demo.md printf '%s\n' "- [ ] demo line"
prep_source demo ok
