#!/usr/bin/env bats
# discover_codebases.sh and the inspect_codebase.sh wrapper (spec §6.13).

setup() {
  REPO="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  DC="$REPO/system/scripts/discover_codebases.sh"
  IC="$REPO/system/scripts/inspect_codebase.sh"
  R="$BATS_TEST_TMPDIR/code"
  mkdir -p "$R"
  RP="$(cd "$R" && pwd -P)"
}

mkrepo() {  # <path> [branch]
  git init -q -b "${2:-main}" "$1"
  git -C "$1" -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m init
}

@test "discover: one object per repo, sorted by path, build and dependency dirs pruned" {
  mkrepo "$R/app"
  git -C "$R/app" remote add origin git@example.com:me/app.git
  mkrepo "$R/two words"
  mkrepo "$R/web"
  mkrepo "$R/web/node_modules/dep"
  mkrepo "$R/web/dist/built"
  mkrepo "$R/deep/a/b/c"
  run "$DC" "$R"
  [ "$status" -eq 0 ]
  [ "${#lines[@]}" -eq 3 ]
  [ "$(jq -r .path <<< "${lines[0]}")" = "$RP/app" ]
  [ "$(jq -r .path <<< "${lines[1]}")" = "$RP/two words" ]
  [ "$(jq -r .path <<< "${lines[2]}")" = "$RP/web" ]
  [ "$(jq -r .remote <<< "${lines[0]}")" = git@example.com:me/app.git ]
  [ "$(jq -r .remote <<< "${lines[1]}")" = null ]
  [ "$(jq -c .worktrees <<< "${lines[2]}")" = "[\"$RP/web\"]" ]
}

@test "discover: worktrees of one repo collapse into one entry" {
  mkrepo "$R/app"
  git -C "$R/app" worktree add -q "$R/app-feature" -b feature
  run "$DC" "$R"
  [ "$status" -eq 0 ]
  [ "${#lines[@]}" -eq 1 ]
  [ "$(jq -r .path <<< "${lines[0]}")" = "$RP/app" ]
  [ "$(jq -c .worktrees <<< "${lines[0]}")" = "[\"$RP/app\",\"$RP/app-feature\"]" ]
}

@test "discover: a bare repo's worktrees resolve to the worktree on its HEAD branch" {
  seed="$BATS_TEST_TMPDIR/seed"
  mkrepo "$seed"
  git clone -q --bare "$seed" "$R/ultron.git"
  git -C "$R/ultron.git" worktree add -q "$R/worktrees/main" main
  git -C "$R/ultron.git" worktree add -q "$R/worktrees/feat" -b feat
  run "$DC" "$R/worktrees"
  [ "$status" -eq 0 ]
  [ "${#lines[@]}" -eq 1 ]
  [ "$(jq -r .path <<< "${lines[0]}")" = "$RP/worktrees/main" ]
  [ "$(jq -c .worktrees <<< "${lines[0]}")" = "[\"$RP/worktrees/feat\",\"$RP/worktrees/main\"]" ]
}

@test "discover: a repo given directly is printed itself" {
  mkrepo "$R/app"
  mkrepo "$R/app/vendor/lib"
  run "$DC" "$R/app"
  [ "$status" -eq 0 ]
  [ "${#lines[@]}" -eq 1 ]
  [ "$(jq -r .path <<< "${lines[0]}")" = "$RP/app" ]
}

@test "discover: a missing directory exits 2" {
  run "$DC" "$R/nope"
  [ "$status" -eq 2 ]
  run "$DC"
  [ "$status" -eq 2 ]
}

@test "inspect: prints one JSON object for the repo" {
  mkrepo "$R/app"
  printf '{"name": "app", "dependencies": {"react": "18"}}' > "$R/app/package.json"
  git -C "$R/app" add package.json
  run "$IC" "$R/app"
  [ "$status" -eq 0 ]
  [ "$(jq -r '.manifests[0].details.notable[0]' <<< "$output")" = react ]
  [ "$(jq -r .path <<< "$output")" = "$RP/app" ]
}

@test "inspect: a relative path is resolved against the caller's directory" {
  mkrepo "$R/app"
  cd "$R"
  run "$IC" app
  [ "$status" -eq 0 ]
  [ "$(jq -r .path <<< "$output")" = "$RP/app" ]
}

@test "inspect: a directory that is not a repo, or no argument, exits 2" {
  run "$IC" "$R"
  [ "$status" -eq 2 ]
  run "$IC"
  [ "$status" -eq 2 ]
}

@test "inspect: at most 5 manifests of a kind unless --all-manifests, with every one counted" {
  mkrepo "$R/app"
  for i in 1 2 3 4 5 6 7; do mkdir -p "$R/app/P$i"; printf '<Project/>' > "$R/app/P$i/P$i.csproj"; done
  git -C "$R/app" add -A
  run "$IC" "$R/app"
  [ "$status" -eq 0 ]
  [ "$(jq '.manifests | length' <<< "$output")" -eq 5 ]
  [ "$(jq -c .manifest_counts <<< "$output")" = '{"dotnet":7}' ]
  run "$IC" --all-manifests "$R/app"
  [ "$status" -eq 0 ]
  [ "$(jq '.manifests | length' <<< "$output")" -eq 7 ]
  run "$IC" --all-manifests
  [ "$status" -eq 2 ]
}
