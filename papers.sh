#!/bin/bash
# PDF -> Markdown pipeline (docling). Drop a PDF in the vault root, run this.
#   ./papers.sh          convert every unconverted PDF once
#   ./papers.sh --watch  poll every 10s (pidfile-guarded)
#   ./papers.sh --stop   stop watcher
#   ./papers.sh --status show watcher state
# Result: <stem>/<stem>.pdf  <stem>/<stem>.md  <stem>/<stem>_artifacts/*.png, then git commit.
# The wiki/ layer is NOT touched here; Claude compiles it via /ingest (see CLAUDE.md).
set -euo pipefail
cd "$(dirname "$0")"

DOCLING="$PWD/.venv-docling/bin/docling"
mkdir -p .papers

convert_pdf() {
  local pdf="$1" dir base md
  dir=$(dirname "$pdf"); base=$(basename "$pdf" .pdf); md="$dir/$base.md"
  [ -f "$md" ] && return 0
  if [ "$dir" = "." ]; then
    mkdir -p "$base"; mv "$pdf" "$base/$base.pdf"
    dir="$base"; pdf="$base/$base.pdf"; md="$dir/$base.md"
  fi
  echo "[$(date '+%H:%M:%S')] converting $base ..."
  # cd into dir so artifacts sit beside the md and refs stay relative
  ( cd "$dir" && "$DOCLING" "$base.pdf" --to md --image-export-mode referenced --output . ) 2>&1 \
    | grep -iE "Finished|ERROR|Traceback" | tail -1 || true
  if [ -f "$md" ]; then
    echo "[$(date '+%H:%M:%S')] OK -> $md"
    if git rev-parse --git-dir >/dev/null 2>&1; then
      git add "$dir/" >/dev/null 2>&1
      git commit -m "Add paper: $base" >/dev/null 2>&1 && echo "[$(date '+%H:%M:%S')] committed $base" || true
    fi
    echo "-> next: tell Claude '/ingest $base'"
  else
    echo "[$(date '+%H:%M:%S')] FAIL $base"
  fi
}

scan() {
  find . -name "*.pdf" -not -path "./.*" -not -path "./debug/*" -not -path "./wiki/*" -print
}

case "${1:-}" in
  --stop)
    if [ -f .papers/watch.pid ]; then
      kill "$(cat .papers/watch.pid)" 2>/dev/null && echo "stopped watcher $(cat .papers/watch.pid)"
      rm -f .papers/watch.pid
    else echo "no watcher running"; fi ;;
  --status)
    if [ -f .papers/watch.pid ] && kill -0 "$(cat .papers/watch.pid)" 2>/dev/null; then
      echo "watcher running (pid $(cat .papers/watch.pid))"; else echo "no watcher"; fi ;;
  --watch)
    if [ -f .papers/watch.pid ] && kill -0 "$(cat .papers/watch.pid)" 2>/dev/null; then
      echo "watcher already running (pid $(cat .papers/watch.pid))"; exit 0
    fi
    echo $$ > .papers/watch.pid
    trap 'rm -f .papers/watch.pid' EXIT
    echo "watching for new PDFs in $PWD ..."
    while true; do
      while read -r pdf; do convert_pdf "$pdf"; done < <(scan)
      sleep 10
    done ;;
  *)
    while read -r pdf; do convert_pdf "$pdf"; done < <(scan) ;;
esac
