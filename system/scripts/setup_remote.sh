#!/bin/bash
# template/origin remote handling and hooksPath (spec §6.11).
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"
# shellcheck source=lib_config.sh
source system/scripts/lib_config.sh
# shellcheck source=lib_git.sh
source system/scripts/lib_git.sh

die() { echo "setup_remote: $2" >&2; exit "$1"; }
usage() { die 2 "usage: setup_remote.sh <url> | --none | --keep | --detect"; }

(( $# == 1 )) || usage
case "$1" in
  --none) mode=none url="" ;;
  --keep) mode=keep url="" ;;
  --detect) mode=detect url="" ;;
  -*) usage ;;
  "") usage ;;
  *) mode=private url="$1" ;;
esac

template="$(head -n 1 system/template_source 2>/dev/null | tr -d '[:space:]')"
[[ -n "$template" ]] || die 1 "system/template_source is missing or empty"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die 1 "the vault is not a git repository"

remote_url() { git remote get-url "$1" 2>/dev/null || true; }

# --detect reports what the other modes would find and changes nothing (spec §11 step 4 asks after it).
if [[ "$mode" == detect ]]; then
  origin="$(remote_url origin)"
  if [[ -n "$origin" ]] && git_url_same "$origin" "$template"; then
    echo "detected: plain clone (origin is the template)"
  elif [[ -n "$origin" ]]; then
    echo "detected: origin is not the template ($origin)"
  else
    echo "detected: no origin"
  fi
  tmpl="$(remote_url template)"
  echo "template remote: ${tmpl:-<none>}"
  exit 0
fi

[[ -f system/config.md ]] || die 1 "system/config.md is missing; run /setup first"
if [[ "$mode" == private ]] && git_url_same "$url" "$template"; then
  die 1 "refusing: $url is the template repository, not a private origin"
fi

if [[ "$mode" != keep ]]; then
  origin="$(remote_url origin)" tmpl="$(remote_url template)"
  if [[ -n "$origin" ]] && git_url_same "$origin" "$template"; then
    if [[ -n "$tmpl" ]]; then
      git remote remove origin
      echo "detected: origin is the template and a template remote exists; removed origin"
    else
      git remote rename origin template
      echo "detected: plain clone; renamed origin -> template"
    fi
  elif [[ -n "$origin" ]]; then
    echo "detected: origin is not the template; origin kept"
  else
    echo "detected: no origin"
  fi
  tmpl="$(remote_url template)"
  if [[ -z "$tmpl" ]]; then
    git remote add template "$template"
    echo "added template remote: $template"
  elif ! git_url_same "$tmpl" "$template"; then
    echo "warning: template remote is $tmpl but system/template_source says $template; left unchanged" >&2
  fi
fi

if [[ "$mode" == private ]]; then
  origin="$(remote_url origin)"
  if [[ -z "$origin" ]]; then
    git remote add origin "$url"
    echo "added origin: $url"
  elif ! git_url_same "$origin" "$url"; then
    git remote set-url origin "$url"
    echo "origin changed: $origin -> $url"
  else
    echo "origin already $url"
  fi
  if ! GIT_TERMINAL_PROMPT=0 timeout 20 git ls-remote --heads origin >/dev/null 2>&1; then
    echo "warning: origin $url is not reachable yet; it is set anyway" >&2
    # An https URL needs a credential prompt that automation cannot answer; on a known host, offer the SSH
    # form when it works without one (#16).
    n="$(git_url_normalize "$url")"
    case "$url" in https://github.com/*|https://gitlab.com/*|https://bitbucket.org/*)
      ssh_url="git@${n%%/*}:${n#*/}.git"
      if GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh} -o BatchMode=yes" \
          timeout 20 git ls-remote --heads "$ssh_url" >/dev/null 2>&1; then
        echo "hint: $ssh_url works without a prompt; to use it, run system/scripts/setup_remote.sh $ssh_url" >&2
      fi ;;
    esac
  fi
fi

set_if_changed() { [[ "$(config_get "$1")" == "$2" ]] || config_set "$1" "$2"; }
set_if_changed remote_mode "$mode"
set_if_changed template_remote "$template"
[[ "$(git config --get core.hooksPath || true)" == .githooks ]] || git config core.hooksPath .githooks
echo "remote_mode: $mode"
