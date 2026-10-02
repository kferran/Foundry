# shellcheck shell=bash
# Git remote helpers (spec §6.11).

# git@host:path ≡ ssh://git@host/path ≡ https://host/path: host lowercased; user, port, trailing "/"
# and ".git" dropped. Local paths and file:// URLs get only the trailing "/" and ".git" rules.
git_url_normalize() {
  local u="${1-}" host path
  while [[ "$u" == */ ]]; do u="${u%/}"; done
  u="${u%.git}"
  while [[ "$u" == */ ]]; do u="${u%/}"; done
  if [[ "$u" == file://* ]]; then
    printf '%s\n' "${u#file://}"
    return
  elif [[ "$u" =~ ^[A-Za-z][A-Za-z0-9+.-]*://([^/]*)(/.*)?$ ]]; then
    host="${BASH_REMATCH[1]##*@}"; host="${host%%:*}"; path="${BASH_REMATCH[2]#/}"
  elif [[ "$u" =~ ^([^/:]+):(.+)$ ]]; then
    host="${BASH_REMATCH[1]##*@}"; path="${BASH_REMATCH[2]#/}"
  else
    printf '%s\n' "$u"
    return
  fi
  printf '%s/%s\n' "${host,,}" "$path"
}

git_url_same() { [[ -n "${1-}" && -n "${2-}" && "$(git_url_normalize "$1")" == "$(git_url_normalize "$2")" ]]; }
