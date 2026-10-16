#!/usr/bin/env bash
# Secret scan: (a) every git-visible file of the working tree and (b) the commit
# range of a push or pull request. Pre-rotation history is out of scope and no
# baseline file is used (D-09).
#
# Usage:   scripts/gitleaks_scan.sh <gitleaks-binary> <base_sha> <head_sha> <floor_sha>
# Exit codes: 0 clean, 1 finding, 2 bad arguments, an unusable range, or an empty or
# unlistable working tree (fail closed).
#
# Range rules, applied in this order (D-09, D-20: validate, then fail closed,
# because gitleaks itself prints an error and exits 0 on an unresolvable --log-opts):
#   1. Sentinel: only the 40-zero base (GitHub's "before" for a new branch) is
#      replaced by the floor, before validation. No other base is replaced.
#   2. The base, the head and the floor must each resolve to a commit, else exit 2
#      (so "not-a-commit", a bogus floor and a missing commit all fail closed).
#   3. Merge-base: a resolvable base that is NOT an ancestor of the head (a PR whose
#      base branch advanced past the fork point, or a force-push whose replaced commit
#      is present) is scanned from merge-base(base, head); a base sharing no history
#      with the head exits 2.
#   4. Floor clamp: a base at or behind the floor is raised to the floor, so history
#      before the key rotation (commit 1fedcd2 and earlier) is never scanned.
#   5. Floor bound: the range is also bounded by "^floor" (everything reachable from
#      the floor is excluded), so a branch that forked before the floor and later
#      merged newer history cannot pull pre-floor commits back into the range.
#   6. Empty range: announced, never silent; the working-tree scan above still ran.
#
# Force-push note: in CI the commit a force-push replaced is normally absent from the
# clone (no ref reaches it), so that run exits 2 under rule 2 - deliberately red and
# consistent with D-20, since force-pushes are forbidden here (D-11, CLAUDE.md). To
# clear it, run the scan with the floor as base:
#   scripts/gitleaks_scan.sh <gitleaks-binary> <floor> HEAD <floor>
# which covers every commit since the floor, and record the result. Never re-run with
# a guessed base.
#
# Output is always redacted (--redact); findings are reported by path and rule only.
set -euo pipefail

if [ "$#" -ne 4 ]; then
  echo "usage: scripts/gitleaks_scan.sh <gitleaks-binary> <base_sha> <head_sha> <floor_sha>" >&2
  exit 2
fi
GL="$1"
BASE="$2"
HEAD_SHA="$3"
FLOOR="$4"
ZERO=0000000000000000000000000000000000000000

if [ ! -x "$GL" ] || [ -d "$GL" ]; then
  echo "gitleaks: binary not found or not executable: $GL" >&2
  exit 2
fi
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "gitleaks: not inside a git repository" >&2
  exit 2
fi

# (a) Working tree: export exactly what git can see, so a local .venv/ or a
# git-ignored .env is never scanned or printed. Fails closed (D-20): the file list is
# captured first so a failing `git ls-files` is seen (a process substitution would hide
# it), and an empty list or an empty export is an error, never a clean scan.
EXPORT=$(mktemp -d)
LIST=$(mktemp)
trap 'rm -rf "$EXPORT" "$LIST"' EXIT
if ! git ls-files -z --cached --others --exclude-standard > "$LIST"; then
  echo "gitleaks: could not list the working-tree files; refusing to report clean" >&2
  exit 2
fi
if [ ! -s "$LIST" ]; then
  echo "gitleaks: working-tree file list is empty; refusing to report clean" >&2
  exit 2
fi
count=0
while IFS= read -r -d '' path; do
  if [ -f "$path" ]; then
    mkdir -p -- "$EXPORT/$(dirname -- "$path")"
    cp -P -- "$path" "$EXPORT/$path"
    count=$((count + 1))
  fi
done < "$LIST"
if [ "$count" -eq 0 ]; then
  echo "gitleaks: working-tree export is empty; refusing to report clean" >&2
  exit 2
fi
echo "== (a) working tree (${count} git-visible files)"
"$GL" dir "$EXPORT" --redact --no-banner --exit-code 1 -l warn

# (b) Commit range.
if [ "$BASE" = "$ZERO" ]; then
  echo "gitleaks: new-branch sentinel base, scanning from the floor"
  BASE="$FLOOR"
fi
git cat-file -e "${BASE}^{commit}" 2>/dev/null || { echo "gitleaks: unusable range: base not found"; exit 2; }
git cat-file -e "${HEAD_SHA}^{commit}" 2>/dev/null || { echo "gitleaks: unusable range: head not found"; exit 2; }
git cat-file -e "${FLOOR}^{commit}" 2>/dev/null || { echo "gitleaks: unusable range: floor not found"; exit 2; }
BASE=$(git rev-parse "${BASE}^{commit}")
HEAD_SHA=$(git rev-parse "${HEAD_SHA}^{commit}")
FLOOR=$(git rev-parse "${FLOOR}^{commit}")

if ! git merge-base --is-ancestor "$BASE" "$HEAD_SHA"; then
  MB=$(git merge-base "$BASE" "$HEAD_SHA") || { echo "gitleaks: unusable range: base and head share no history"; exit 2; }
  echo "gitleaks: base ${BASE:0:7} is not an ancestor of head ${HEAD_SHA:0:7} (PR base branch advanced, or a force-push); scanning from merge-base ${MB:0:7}"
  BASE="$MB"
fi

if [ "$BASE" != "$FLOOR" ] && git merge-base --is-ancestor "$BASE" "$FLOOR"; then
  echo "gitleaks: range base ${BASE:0:7} is at or behind the floor; scanning from the floor ${FLOOR:0:7} (pre-rotation history is out of scope, D-09)"
  BASE="$FLOOR"
fi

n=$(git rev-list --count "${BASE}..${HEAD_SHA}" "^${FLOOR}")
echo "== (b) commit range ${BASE:0:7}..${HEAD_SHA:0:7} excluding history up to the floor (${n} commits)"
if [ "$n" -eq 0 ]; then
  echo "gitleaks: commit range is empty (the head adds no commits beyond the range base); the working-tree scan above still ran"
else
  "$GL" git . --redact --no-banner --exit-code 1 -l warn --log-opts="${BASE}..${HEAD_SHA} ^${FLOOR}"
fi
echo "gitleaks: clean"
