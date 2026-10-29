#!/bin/bash
# The brief unit's ExecStart (#299; brief retry spec §3.1, plan ruling 1): the prep, then the brief. A brief the
# publish gate rejected (exit 5) gets one fresh run, its prep first, so its inputs match the page it now sees. The
# first rejection raises no alert (run_headless.sh sees BRIEF_RETRY_PENDING); a second raises one. Any other exit ends
# the run as it is. Exit: the last brief's.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
for attempt in 1 2; do
  system/scripts/brief_prep.sh || true   # a failed prep never stops the brief, as ExecStartPre=- did
  rc=0
  if (( attempt == 1 )); then
    BRIEF_RETRY_PENDING=1 system/scripts/run_headless.sh brief || rc=$?
  else
    system/scripts/run_headless.sh brief || rc=$?
  fi
  if (( rc != 5 )); then exit "$rc"; fi
  if (( attempt == 1 )); then sleep "${BRIEF_RETRY_WAIT:-60}"; fi
done
system/scripts/alert.py intake "the brief was rejected twice; see the publish.json of today's brief runs in system/logs/runs/" \
  || true
exit 5
