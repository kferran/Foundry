# @@description@@, read live every brief. Sourced by brief_prep.sh in a subshell, from the vault root, with PREP_DATE,
# PREP_DIR and the prep_* functions (extensions spec §3). Writes sections/@@name@@.md: the fetch's lines, or an empty
# file when the fetch failed. The brief prints the lines once the feature writes brief/section.md, its prompt.
: > "$PREP_DIR/sections/@@name@@.md"
rc=0
prep_write sections/@@name@@.md extensions/@@name@@/scripts/@@name@@_fetch.sh || rc=$?
if (( rc == 0 )); then
  prep_source @@name@@ ok
else
  prep_source @@name@@ failed "$(prep_reason @@name@@_fetch "$rc")"
  prep_unavailable "@@name@@: $(prep_reason @@name@@_fetch "$rc")"
fi
# A fetch failure is recorded above; the section stays empty and the brief still runs.
exit 0
