#!/usr/bin/env bash
# Prove the range rules of scripts/gitleaks_scan.sh and redacted detection in
# throwaway repositories created OUTSIDE this repository.
#
# Usage:   scripts/gitleaks_selftest.sh <gitleaks-binary>
# Exit codes: 0 every scenario matched, 1 any mismatch, 2 bad arguments.
#
# Scenarios (cwd of every scan = the throwaway repository):
#   advanced-pr-base        base A (PR base branch moved on), head C, floor R -> exit 0, scanned from the merge-base
#   advanced-pr-base-leak   base A, head L (planted value), floor R           -> exit 1, value absent from output
#   unrelated-history       base U (no shared history), head C, floor R       -> exit 2
#   working-tree-leak       base R, head L, floor R, leaky branch checked out -> exit 1, value absent from output
#   merged-prefloor-branch  an old branch (base X) that merged post-floor history (head Z) while the
#                           pre-floor history holds a planted value          -> exit 0 (floor bound);
#                           a control scan of X..Z without the bound         -> exit 1 (the scenario is real)
# The planted values are generated at run time, kept in shell variables and throwaway
# files, and never echoed.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: scripts/gitleaks_selftest.sh <gitleaks-binary>" >&2
  exit 2
fi
if [ ! -x "$1" ] || [ -d "$1" ]; then
  echo "selftest: gitleaks binary not found or not executable: $1" >&2
  exit 2
fi
GL=$(realpath -- "$1")
SCAN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/gitleaks_scan.sh"

INVOKER_TOP=$(git rev-parse --show-toplevel 2>/dev/null || true)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
if [ -n "$INVOKER_TOP" ]; then
  case "$WORK/" in
    "$INVOKER_TOP"/*)
      echo "selftest: refusing a work directory inside the repository $INVOKER_TOP" >&2
      exit 2
      ;;
  esac
fi

g() { git -c user.name=selftest -c user.email=selftest@example.invalid -c commit.gpgsign=false "$@"; }
# AWS-shaped value built at run time from 16 distinct symbols: the aws-access-token rule has no
# stopword list and its entropy floor is always cleared, so detection is deterministic
# (a random urlsafe token is sometimes dropped by the generic-api-key stopwords or entropy gate).
gen_secret() {
  python3 -c "import secrets; print('AK' + 'IA' + ''.join(secrets.SystemRandom().sample('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567', 16)))"
}

SECRET=$(gen_secret)
OLD_SECRET=$(gen_secret)
OUT="$WORK/out.txt"
REPO="$WORK/repo"
mkdir "$REPO"
cd "$REPO"
g init -q
g checkout -q -b main

# Root commit R (clean).
echo "clean root file" > README.txt
g add README.txt
g commit -q -m "R: clean root"
R=$(git rev-parse HEAD)

# base-advanced = R + A (the PR base branch moving on after the fork).
g checkout -q -b base-advanced
echo "base branch moved on" > advanced.txt
g add advanced.txt
g commit -q -m "A: clean base advance"
A=$(git rev-parse HEAD)

# clean-pr = R + C.
g checkout -q "$R"
g checkout -q -b clean-pr
echo "clean pull request change" > change.txt
g add change.txt
g commit -q -m "C: clean PR commit"
C=$(git rev-parse HEAD)

# leaky-pr = R + L (one-line Python file with a planted high-entropy assignment).
g checkout -q "$R"
g checkout -q -b leaky-pr
printf 'api_key = "%s"\n' "$SECRET" > leak.py
g add leak.py
g commit -q -m "L: planted value"
L=$(git rev-parse HEAD)

# unrelated = orphan root U.
g checkout -q --orphan unrelated
g rm -rfq .
echo "unrelated history" > unrelated.txt
g add unrelated.txt
g commit -q -m "U: unrelated root"
U=$(git rev-parse HEAD)

# Pre-floor scenario: rot-main = R + K (planted value, "rotated key") + F (floor, value removed) + M (clean).
g checkout -q "$R"
g checkout -q -b rot-main
printf 'api_key = "%s"\n' "$OLD_SECRET" > rotated.py
g add rotated.py
g commit -q -m "K: pre-floor planted value"
g rm -q rotated.py
g commit -q -m "F: floor, value removed"
F=$(git rev-parse HEAD)
echo "post-floor work" > post.txt
g add post.txt
g commit -q -m "M: clean post-floor commit"
# old-feature = R + X, then merges rot-main (Z); the previous PR tip X is neither an ancestor nor a descendant of F.
g checkout -q "$R"
g checkout -q -b old-feature
echo "old feature work" > feature.txt
g add feature.txt
g commit -q -m "X: clean old feature commit"
X=$(git rev-parse HEAD)
g merge -q --no-edit rot-main
Z=$(git rev-parse HEAD)

FAILED=0
RC=0

run_scan() { # base head floor -> RC, output in $OUT
  RC=0
  bash "$SCAN" "$GL" "$1" "$2" "$3" > "$OUT" 2>&1 || RC=$?
}
leaked() { grep -qF -- "$1" "$OUT"; }
report() { # case-name verdict
  if [ "$2" = ok ]; then
    echo "selftest: $1: ok"
  else
    echo "selftest: $1: FAILED (exit $RC)"
    FAILED=1
  fi
}

# (i) advanced PR base: scanned from the merge-base, clean.
g checkout -q base-advanced
run_scan "$A" "$C" "$R"
v=bad
if [ "$RC" -eq 0 ] && grep -q "not an ancestor" "$OUT" && grep -q "merge-base" "$OUT"; then v=ok; fi
report "advanced-pr-base" "$v"

# (ii) advanced PR base with a planted value on the head side: caught, redacted.
run_scan "$A" "$L" "$R"
v=bad
if [ "$RC" -eq 1 ] && ! leaked "$SECRET"; then v=ok; fi
report "advanced-pr-base-leak" "$v"

# (iii) no shared history: fails closed.
run_scan "$U" "$C" "$R"
v=bad
if [ "$RC" -eq 2 ]; then v=ok; fi
report "unrelated-history" "$v"

# (iv) working-tree detection with the leaky branch checked out.
g checkout -q leaky-pr
run_scan "$R" "$L" "$R"
v=bad
if [ "$RC" -eq 1 ] && ! leaked "$SECRET"; then v=ok; fi
report "working-tree-leak" "$v"

# (v) merged pre-floor branch: the floor bound keeps pre-floor commits out of the range.
g checkout -q old-feature
run_scan "$X" "$Z" "$F"
v=bad
if [ "$RC" -eq 0 ] && ! leaked "$OLD_SECRET"; then v=ok; fi
report "merged-prefloor-branch" "$v"

# (v) control: the same range without the floor bound does reach the planted value.
CONTROL_RC=0
"$GL" git . --redact --no-banner --exit-code 1 -l warn --log-opts="${X}..${Z}" > "$OUT" 2>&1 || CONTROL_RC=$?
RC=$CONTROL_RC
v=bad
if [ "$CONTROL_RC" -eq 1 ] && ! leaked "$OLD_SECRET"; then v=ok; fi
report "merged-prefloor-control" "$v"

if [ "$FAILED" -eq 0 ]; then
  echo "selftest: all scenarios passed"
  exit 0
fi
echo "selftest: one or more scenarios FAILED" >&2
exit 1
