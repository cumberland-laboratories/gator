#!/bin/bash
set -euo pipefail
# Canonical release script for Gator Individual (public PyPI).
# This is the ONLY authorized path for public releases.
# Do not run twine directly.

cd "$(dirname "$0")/.."

echo "Building Gator Individual..."
rm -rf dist/
python -m build

echo "Removing sdist (enterprise source must not leave this machine)..."
rm -f dist/*.tar.gz

if ls dist/*.whl 1>/dev/null 2>&1; then
    echo "Uploading wheel to PyPI..."
    python -m twine upload dist/*.whl
    echo "Done. Wheel published to PyPI."
else
    echo "Error: no wheel found in dist/"
    exit 1
fi
