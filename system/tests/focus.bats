#!/usr/bin/env bats
# focus_stats.sh (spec §6.6) and track_obsidian.sh (spec §6.7).
load helpers

setup() {
  make_vault
  cd "$V"
  mkdir -p system/logs
  FS="$V/system/scripts/focus_stats.sh"
  TR="$V/system/scripts/track_obsidian.sh"
  L=system/logs/obsidian_focus_2026-10-01.log
}

sample() { printf '[%s] %s\n' "$1" "$2" >> "$L"; }

@test "focus_stats: a missing log reports no focus data" {
  run "$FS" 2026-10-01
  [ "$status" -eq 0 ]
  [ "${lines[0]}" = "# Focus: 2026-10-01" ]
  [ "${lines[1]}" = "no focus data" ]
}

@test "focus_stats: a missing or invalid date exits 2" {
  run "$FS"
  [ "$status" -eq 2 ]
  run "$FS" 2026-02-30
  [ "$status" -eq 2 ]
  run "$FS" 2026-10-01 extra
  [ "$status" -eq 2 ]
}

@test "focus_stats: top 10 notes by samples, ties by name, minutes = samples x 30 s" {
  t=0
  for i in $(seq 1 12); do
    for _ in $(seq 1 "$i"); do
      sample "$(date -u -d "@$(( 8 * 3600 + t * 30 ))" +%H:%M:%S)" "N$(printf '%02d' "$i")"
      t=$(( t + 1 ))
    done
  done
  sample 12:00:00 Alpha
  run "$FS" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx '| N12 | 12 | 6 |' <<< "$output"
  grep -qx '| N11 | 11 | 5.5 |' <<< "$output"
  grep -qx '| N03 | 3 | 1.5 |' <<< "$output"
  [ "$(grep -c '^| N[0-9]' <<< "$output")" -eq 10 ]
  [[ "$output" != *"| N02 |"* ]]
  [[ "$output" != *"| Alpha |"* ]]
  first="$(grep -n '| N12 |' <<< "$output" | cut -d: -f1)"
  second="$(grep -n '| N11 |' <<< "$output" | cut -d: -f1)"
  [ "$first" -lt "$second" ]
}

@test "focus_stats: a window is flagged at 5 switches, not at 4" {
  for t in 09:15:00:A 09:15:30:B 09:16:00:A 09:16:30:B 09:17:00:A 09:17:30:B; do sample "${t%:*}" "${t##*:}"; done
  # The 10:00 window opens on the note that was focused last, so it holds exactly 4 switches.
  for t in 10:00:00:B 10:00:30:A 10:01:00:B 10:01:30:A 10:02:00:B; do sample "${t%:*}" "${t##*:}"; done
  run "$FS" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qxF -- '- **Focus Fragmentation Warning** 09:15–09:30: 5 switches' <<< "$output"
  [[ "$output" != *"10:00–10:15"* ]]
}

@test "focus_stats: no fragmentation says so" {
  sample 09:00:00 A
  sample 09:00:30 A
  run "$FS" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx 'No fragmentation windows.' <<< "$output"
}

@test "focus_stats: torn and malformed lines are skipped" {
  sample 09:00:00 Kafka
  printf 'garbage\n[25:00:00] Bad hour\n[09:00:30]NoSpace\n' >> "$L"
  printf '[10:00' >> "$L"
  run "$FS" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx '| Kafka | 1 | 0.5 |' <<< "$output"
  [ "$(grep -c '^| ' <<< "$output")" -eq 2 ]  # the header and Kafka
}

@test "focus_stats: a log of only malformed lines is no focus data" {
  printf 'garbage\n[10:00' > "$L"
  run "$FS" 2026-10-01
  [ "$status" -eq 0 ]
  [ "${lines[1]}" = "no focus data" ]
}

@test "focus_stats: note names keep ' - ' and escape '|' for the table" {
  sample 09:00:00 'Q3 - plan | v2'
  run "$FS" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qxF '| Q3 - plan \| v2 | 1 | 0.5 |' <<< "$output"
}
