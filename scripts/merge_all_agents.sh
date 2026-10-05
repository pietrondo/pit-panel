#!/bin/bash
# Merge all unmerged origin branches into current HEAD.
# - Clean merge: keep it.
# - Conflict only in agent logs (.jules/*, pr_description.md): union-resolve and commit.
# - Any code conflict: abort and record for manual resolution.
set -u
cd "$(git rev-parse --show-toplevel)"

BRANCHES=$(git branch -r --no-merged HEAD | sed 's/^ *//' | grep -v 'HEAD ->')

# order: ascending commit count (1-commit branches first)
ORDERED=$(
  for b in $BRANCHES; do
    n=$(git rev-list --count HEAD.."$b")
    echo "$n $b"
  done | sort -n | awk '{print $2}'
)

for b in $ORDERED; do
  short=${b#origin/}
  if git merge --no-edit --no-ff "$b" >/dev/null 2>&1; then
    echo "OK $short"
    continue
  fi
  files=$(git diff --name-only --diff-filter=U)
  code_files=$(printf '%s\n' "$files" | grep -vE '^\.jules/|^pr_description\.md$' | grep -v '^$' || true)
  if [ -z "$code_files" ]; then
    for f in $files; do
      s2=$(git ls-files -u -- "$f" | awk '$3==2{print $2}')
      s3=$(git ls-files -u -- "$f" | awk '$3==3{print $2}')
      if [ -n "$s2" ] && [ -n "$s3" ]; then
        git show ":1:$f" > /tmp/mf_base 2>/dev/null || : > /tmp/mf_base
        git show ":2:$f" > /tmp/mf_ours
        git show ":3:$f" > /tmp/mf_theirs
        git merge-file --union /tmp/mf_ours /tmp/mf_base /tmp/mf_theirs
        cp /tmp/mf_ours "$f"
      elif [ -n "$s2" ]; then
        git checkout --ours -- "$f"
      else
        git checkout --theirs -- "$f"
      fi
      git add -- "$f"
    done
    git commit --no-edit >/dev/null 2>&1 || git commit -m "merge: $short (agent logs)" >/dev/null 2>&1
    echo "LOGRES $short"
  else
    git merge --abort
    echo "CODECONF $short"
  fi
done
echo "DONE"
