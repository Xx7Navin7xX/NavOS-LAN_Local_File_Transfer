#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# 1. Detect Python 3
find_python() {
    if command -v python3 >/dev/null 2>&1; then
        if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
            echo "python3"
            return 0
        fi
    fi
    if command -v python >/dev/null 2>&1; then
        if python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
            echo "python"
            return 0
        fi
    fi
    # Check common Homebrew / Framework locations on macOS
    for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/3.*/bin/python3; do
        if [ -x "$p" ]; then
            echo "$p"
            return 0
        fi
    done
    return 1
}

PYTHON_BIN=$(find_python || true)

# 2. If not found, attempt automatic installation
if [ -z "$PYTHON_BIN" ]; then
    echo "================================================================="
    echo " Python 3 was not detected on this Mac."
    echo " Attempting automatic installation..."
    echo "================================================================="
    echo ""

    # Try Homebrew if present
    if command -v brew >/dev/null 2>&1; then
        echo "Installing Python 3 via Homebrew..."
        brew install python3
    elif command -v xcode-select >/dev/null 2>&1; then
        echo "Prompting to install Apple Command Line Tools (includes Python 3)..."
        xcode-select --install || true
        echo "Please complete the Apple Command Line Tools installation prompt, then run this script again."
        exit 1
    else
        echo "Downloading official macOS Python installer from python.org..."
        TMP_PKG="/tmp/python_installer_$$.pkg"
        curl -fsSL -o "$TMP_PKG" "https://www.python.org/ftp/python/3.12.5/python-3.12.5-macos11.pkg"
        echo "Running Python installer (you may be prompted for your macOS password)..."
        sudo installer -pkg "$TMP_PKG" -target /
        rm -f "$TMP_PKG"
    fi

    PYTHON_BIN=$(find_python || true)

    if [ -z "$PYTHON_BIN" ]; then
        echo ""
        echo "Error: Could not automatically install Python 3."
        echo "Please download and install Python 3 from https://www.python.org/downloads/mac-osx/"
        exit 1
    fi
fi

echo "Starting Pura Services with $PYTHON_BIN..."
exec "$PYTHON_BIN" server.py "$@"
