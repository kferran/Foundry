# The Market line (market watch spec §3.5): today's market page, or why there is none, as one line. Sourced by
# brief_prep.sh in a subshell, from the vault root, with PREP_DATE, PREP_DIR and the prep_* functions (extensions
# spec §3). The fetch's own reading reaches the Sources line through the smoke row.
prep_write sections/market.md extensions/market/scripts/market_page.py line "$PREP_DATE"
exit 0
