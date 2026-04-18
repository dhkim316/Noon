#!/bin/sh

set -eu

usage() {
  cat <<'EOF'
Usage: ./git_sync.sh -m "Vn.n"

Options:
  -m  Commit message to use for the sync
  -h  Show this help message
EOF
}

message=""

while getopts "m:h" opt; do
  case "$opt" in
    m)
      message=$OPTARG
      ;;
    h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 1
      ;;
  esac
done

shift $((OPTIND - 1))

if [ -z "$message" ] || [ "$#" -ne 0 ]; then
  usage >&2
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: this script must be run inside a git repository." >&2
  exit 1
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "Error: remote 'origin' is not configured." >&2
  exit 1
fi

branch=$(git branch --show-current)

if [ -z "$branch" ]; then
  echo "Error: could not determine the current branch." >&2
  exit 1
fi

echo "Current branch: $branch"
echo "Staging all changes..."
git add -A

if ! git diff --cached --quiet; then
  echo "Creating commit: $message"
  git commit -m "$message"
else
  echo "No staged changes to commit."
fi

echo "Pushing to origin/$branch..."
git push -u origin "$branch"

echo "Sync complete."
