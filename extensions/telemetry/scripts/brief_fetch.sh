#!/bin/bash
# The brief prep's last fetch, bounded so a hung source cannot hold the brief toward its unit limit (#122).
# Exits 124 when the fetch ran past the bound; otherwise telemetry_fetch.py's own exit code.
exec timeout -k 5 "${TELEMETRY_PREP_TIMEOUT:-120}" "$(dirname "$0")/telemetry_fetch.py"
