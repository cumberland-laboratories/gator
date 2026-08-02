#!/bin/bash
# Build the gator-enterprise-cli wheel for distribution.
# Output: dist/gator_enterprise_cli-<version>-py3-none-any.whl
#
# Install on developer machines:
#   pip install gator_enterprise_cli-0.1.0-py3-none-any.whl

set -e
cd "$(dirname "$0")"

rm -rf dist/ build/ *.egg-info
pip wheel . -w dist/ --no-deps
echo ""
echo "Built:"
ls -la dist/*.whl
echo ""
echo "Install with:"
echo "  pip install dist/$(ls dist/*.whl | head -1 | xargs basename)"
