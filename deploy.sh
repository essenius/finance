#!/usr/bin/env bash
set -euo pipefail

DEV_ROOT="$(cd "$(dirname "$0")" && pwd)"
PYPROJECT="$DEV_ROOT/pyproject.toml"
PROD_ROOT="$HOME/prod/finance"
PROD_VENV="$PROD_ROOT/venv"


echo "=== Dev root: $DEV_ROOT ==="
echo "=== Prod root: $PROD_ROOT ==="

# Safety check
if [ ! -f "$PYPROJECT" ]; then
    echo "ERROR: deploy.sh must be in the dev project root"
    exit 1
fi

echo "=== Bumping version in pyproject.toml ==="
# Extract current version
CURRENT_VERSION=$(grep '^version =' "$PYPROJECT" | sed -E 's/version = "([0-9]+)\.([0-9]+)\.([0-9]+)"/\1 \2 \3/')
read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

# Increment patch
NEW_PATCH=$((PATCH + 1))
NEW_VERSION="$MAJOR.$MINOR.$NEW_PATCH"

# Replace in file
sed -i "s/version = \"$MAJOR.$MINOR.$PATCH\"/version = \"$NEW_VERSION\"/" "$PYPROJECT"

echo "Version bumped: $MAJOR.$MINOR.$PATCH → $NEW_VERSION"

echo "=== Cleaning old build artifacts ==="
rm -rf "$DEV_ROOT/dist" "$DEV_ROOT/build" "$DEV_ROOT/finance.egg-info"

echo "=== Building wheel ==="

cd "$DEV_ROOT"
python -m build

WHEEL=$(ls dist/*.whl | head -n 1)
echo "Built wheel: $WHEEL"

echo "=== Copying wheel to prod ==="
cp "$WHEEL" "$PROD_ROOT/"

WHEEL_FILE=$(basename "$WHEEL")

echo "=== Installing wheel in prod venv ==="
"$PROD_VENV/bin/pip" install --upgrade "$PROD_ROOT/$WHEEL_FILE"

echo "=== Deployment complete ==="
echo "Deployed version: $NEW_VERSION"
