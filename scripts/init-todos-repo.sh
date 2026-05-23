#!/usr/bin/env bash
# Initialize the data repo (private) that backs the markdown todos.
# Run this once. Creates the folder structure, applies the label taxonomy,
# and pushes the initial commit.
set -euo pipefail

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not found. install with: brew install gh"
  exit 1
fi

TODOS_DIR="${TODOS_DIR:-$HOME/iCloud Drive/todos}"
TODOS_REPO="${TODOS_REPO:-}"

if [ -z "$TODOS_REPO" ]; then
  echo "TODOS_REPO is not set (e.g. your-user/todos)"
  exit 1
fi

mkdir -p "$TODOS_DIR"
cd "$TODOS_DIR"

if [ ! -d .git ]; then
  git init -b main
fi

# folder layout. Owners come from $TODOS_OWNERS (default: user-a,user-b);
# the "shared" namespace is always included.
IFS=',' read -ra OWNER_LIST <<< "${TODOS_OWNERS:-user-a,user-b}"
OWNER_LIST+=("shared")
for owner in "${OWNER_LIST[@]}"; do
  owner="${owner// /}"
  [ -z "$owner" ] && continue
  for sub in inbox active blocked needs_review someday done; do
    mkdir -p "$owner/$sub"
    touch "$owner/$sub/.gitkeep"
  done
done
mkdir -p contacts _templates
touch contacts/.gitkeep _templates/.gitkeep

cat > .gitignore <<'EOF'
.DS_Store
.obsidian/workspace*
EOF

# README inside the data repo
cat > README.md <<'EOF'
# todos

Backing data repo for Life Ops. Plain markdown, one file per item.
See life-ops-system.md in the Life Ops repo for the full spec.
EOF

git add -A
git commit -m "initial layout" || true

# create the repo if missing, otherwise just push
if ! gh repo view "$TODOS_REPO" >/dev/null 2>&1; then
  gh repo create "$TODOS_REPO" --private --source=. --remote=origin --push
else
  if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin "git@github.com:${TODOS_REPO}.git"
  fi
  git push -u origin main
fi

# label taxonomy. Owner labels come from $TODOS_OWNERS so households with
# different members still get clean labels.
OWNER_LABELS=()
PALETTE=("#1f77b4" "#9467bd" "#2ca02c" "#ff7f0e" "#17becf" "#bcbd22")
i=0
for owner in "${OWNER_LIST[@]}"; do
  owner="${owner// /}"
  [ -z "$owner" ] && continue
  if [ "$owner" = "shared" ]; then
    OWNER_LABELS+=("owner:shared|#8c564b")
  else
    OWNER_LABELS+=("owner:$owner|${PALETTE[$((i % ${#PALETTE[@]}))]}")
    i=$((i+1))
  fi
done

LABELS=(
  "${OWNER_LABELS[@]}"
  "status:inbox|#bdbdbd"
  "status:active|#2ca02c"
  "status:blocked|#d62728"
  "status:delegated|#17becf"
  "status:needs-review|#ff7f0e"
  "status:done|#9e9e9e"
  "q1:urgent-important|#d62728"
  "q2:not-urgent-important|#2ca02c"
  "q3:urgent-not-important|#ff7f0e"
  "q4:eliminate|#bdbdbd"
  "type:maintenance|#a55194"
  "type:errand|#ce6dbd"
  "type:project|#7b4173"
  "type:research|#5254a3"
  "type:family|#e377c2"
  "type:vehicles|#393b79"
  "type:yard|#637939"
  "type:finance|#8c6d31"
)

for entry in "${LABELS[@]}"; do
  name="${entry%%|*}"; color="${entry##*|}"
  gh label create "$name" --color "${color#\#}" --repo "$TODOS_REPO" 2>/dev/null \
    || gh label edit "$name" --color "${color#\#}" --repo "$TODOS_REPO" || true
done

echo "==> done. todos repo ready at $TODOS_REPO"
