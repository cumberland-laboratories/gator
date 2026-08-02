#!/bin/bash
# test-install-cycle.sh — Repeatable Gator 1.0 install test cycle.
#
# Creates a clean test environment, clones the public repo, creates a
# dummy project, and gatorizes it. Run repeatedly without mess.
#
# Usage:
#   bash scripts/test-install-cycle.sh          # full reset + install
#   bash scripts/test-install-cycle.sh --keep   # skip clone, just re-gatorize
#
# After running, cd /c/Users/curator/gator-test/my-project and test.

set -e

TEST_DIR="/c/Users/curator/gator-test"
GATOR_REPO="https://github.com/cumberland-laboratories/gator.git"

echo ""
echo "  gator install test cycle"
echo ""

# --- Reset ---
if [ "$1" != "--keep" ]; then
    echo "  Resetting $TEST_DIR..."
    rm -rf "$TEST_DIR"
    mkdir -p "$TEST_DIR"

    echo "  Cloning Gator 1.0..."
    git clone "$GATOR_REPO" "$TEST_DIR/gator" 2>&1 | tail -1
    echo "  ✓ Cloned"
else
    echo "  --keep: skipping clone, reusing existing $TEST_DIR/gator"
    # Just nuke the test project
    rm -rf "$TEST_DIR/my-project"
fi

# --- Create dummy project ---
echo "  Creating test project..."
mkdir -p "$TEST_DIR/my-project"
cd "$TEST_DIR/my-project"
git init -q
git config user.email "test@test.com"
git config user.name "Test User"

# Minimal project structure
mkdir -p src
cat > src/app.py << 'PYEOF'
"""Simple app module."""

def greet(name: str) -> str:
    """Return a greeting."""
    return f"Hello, {name}!"

def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b
PYEOF

cat > README.md << 'MDEOF'
# My Project

A test project for Gator install validation.
MDEOF

git add -A
git commit -q -m "Initial project setup"
echo "  ✓ Test project created"

# --- Gatorize ---
echo "  Gatorizing..."
echo ""
bash "$TEST_DIR/gator/gator-engine/scripts/gatorize.sh" "$TEST_DIR/my-project"

echo ""
echo "  ─────────────────────────────────"
echo "  Test environment ready:"
echo ""
echo "    Command post: $TEST_DIR/gator"
echo "    Test project: $TEST_DIR/my-project"
echo ""
echo "  Next steps:"
echo "    cd $TEST_DIR/my-project"
echo "    # Open in Claude Code / Codex / Gemini"
echo "    # Edit src/app.py, try to commit without charter update"
echo "    # Update .gator/charters/, commit again"
echo ""
echo "  To reset: bash scripts/test-install-cycle.sh"
echo "  ─────────────────────────────────"
