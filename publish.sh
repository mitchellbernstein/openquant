#!/bin/bash
# openquant-cli PyPI Publishing Script
# ======================================
#
# BEFORE RUNNING:
# 1. Create a PyPI account at https://pypi.org/account/register/
# 2. Create a TestPyPI account at https://test.pypi.org/account/register/
# 3. Generate API tokens:
#    - PyPI:     https://pypi.org/manage/account/token/
#    - TestPyPI: https://test.pypi.org/manage/account/token/
# 4. Edit ~/.pypirc and replace the placeholder tokens with your real ones
#
# USAGE:
#   ./publish.sh test      # Upload to TestPyPI only
#   ./publish.sh prod      # Upload to real PyPI
#   ./publish.sh both      # Upload to TestPyPI first, then PyPI

set -e
cd "$(dirname "$0")"

if [ -z "$1" ]; then
    echo "Usage: $0 [test|prod|both]"
    exit 1
fi

# Check that dist files exist
if [ -z "$(ls dist/*.whl dist/*.tar.gz 2>/dev/null)" ]; then
    echo "No dist files found. Building..."
    pip3 install build
    python3 -m build
fi

echo "Dist files:"
ls -la dist/

case "$1" in
    test)
        echo "=== Uploading to TestPyPI ==="
        python3 -m twine upload --repository testpypi dist/*
        echo ""
        echo "Test install: pip install --index-url https://test.pypi.org/simple/ openquant-cli"
        ;;
    prod)
        echo "=== Uploading to PyPI ==="
        python3 -m twine upload dist/*
        echo ""
        echo "Install: pip install openquant-cli"
        ;;
    both)
        echo "=== Step 1: Uploading to TestPyPI ==="
        python3 -m twine upload --repository testpypi dist/*
        echo ""
        echo "TestPyPI upload succeeded!"
        echo ""
        echo "=== Step 2: Uploading to PyPI ==="
        python3 -m twine upload dist/*
        echo ""
        echo "PyPI upload succeeded!"
        echo "Install: pip install openquant-cli"
        ;;
    *)
        echo "Unknown target: $1. Use test, prod, or both."
        exit 1
        ;;
esac
