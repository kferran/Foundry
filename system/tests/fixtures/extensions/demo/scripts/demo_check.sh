#!/bin/bash
# Fixture smoke entry: DEMO_CHECK_MODE=expired prints an auth failure and exits 6; otherwise it says ok and exits 0.
if [[ "${DEMO_CHECK_MODE:-}" == "expired" ]]; then
  echo "demo_check: auth: HTTP 401" >&2
  exit 6
fi
echo "demo_check: ok"
