#!/usr/bin/env bash
# Publishes the public demo to a Hugging Face Space.
#
#   scripts/publish_space.sh https://huggingface.co/spaces/<user>/<space>
#   scripts/publish_space.sh --dry-run <folder>      builds what would be sent into <folder> and stops
#
# Only files that are COMMITTED in this repository are sent, so nothing untracked (an .env file, a
# virtual environment, data) can end up in the Space. Two things differ from the repository:
#   - README.md is the Space's own (deploy/huggingface/README.md), which carries the Space settings
#   - the Dockerfile gets a last line that switches demo mode on, so it cannot be forgotten
# The push replaces the history of the Space: it is a copy of the project, not where it lives.
# See deploy/huggingface/DEPLOY.md.
set -euo pipefail

fail() { echo "error: $*" >&2; exit 1; }

usage() {
  echo "usage: scripts/publish_space.sh https://huggingface.co/spaces/<user>/<space>" >&2
  echo "       scripts/publish_space.sh --dry-run <folder>" >&2
  exit 2
}

[ $# -ge 1 ] || usage

dry_run=false
if [ "$1" = "--dry-run" ]; then
  [ $# -eq 2 ] || usage
  dry_run=true
  out="$2"
else
  [ $# -eq 1 ] || usage
  url="$1"
  # Refuse anything that is not a Space, so this can never force-push over another repository.
  case "$url" in
    https://huggingface.co/spaces/*/*|git@hf.co:spaces/*/*) ;;
    *) fail "'$url' does not look like a Hugging Face Space (https://huggingface.co/spaces/<user>/<space>)" ;;
  esac
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
git -C "$root" rev-parse --git-dir >/dev/null 2>&1 || fail "$root is not a git repository"
commit="$(git -C "$root" rev-parse --short HEAD)" || fail "the repository has no commit yet"

if [ -n "$(git -C "$root" status --porcelain)" ]; then
  echo "note: there are uncommitted changes. They are NOT published; only commit $commit is." >&2
fi

if $dry_run; then
  mkdir -p "$out"
  [ -z "$(ls -A "$out")" ] || fail "'$out' is not empty"
  dest="$out"
else
  dest="$(mktemp -d)"
  trap 'rm -rf "${dest:?}"' EXIT
fi

git -C "$root" archive HEAD | tar -x -C "$dest"

[ -f "$dest/deploy/huggingface/README.md" ] || fail "deploy/huggingface/README.md is not committed"
[ -f "$dest/Dockerfile" ] || fail "the Dockerfile is not committed"

cp "$dest/deploy/huggingface/README.md" "$dest/README.md"
{
  echo ""
  echo "# Public demo: limits, a daily reset and a database of its own (see routeiq/demo.py)"
  echo "ENV ROUTEIQ_DEMO=1"
} >> "$dest/Dockerfile"

if $dry_run; then
  echo "Built what would be sent (commit $commit) in $out"
  exit 0
fi

cd "$dest"
git init -q -b main
git add -A
git -c user.name="RouteIQ publisher" -c user.email="publisher@localhost" commit -q -m "Publish RouteIQ demo (commit $commit)"
echo "Sending commit $commit to $url"
git push --force "$url" main
echo "Done. The Space now builds the image; follow it in the Space's Logs tab."
