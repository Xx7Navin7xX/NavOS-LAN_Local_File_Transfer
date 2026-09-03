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
    return 1
}

PYTHON_BIN=$(find_python || true)

# 2. If not found, attempt automatic installation via system package manager
if [ -z "$PYTHON_BIN" ]; then
    echo "================================================================="
    echo " Python 3 was not detected on this system."
    echo " Attempting automatic installation via package manager..."
    echo "================================================================="
    echo ""

    SUDO=""
    if [ "$(id -u)" -ne 0 ]; then
        if command -v sudo >/dev/null 2>&1; then
            SUDO="sudo"
        else
            echo "Warning: Not running as root and 'sudo' command not found."
        fi
    fi

    # Debian / Ubuntu / Mint / Pop_OS
    if command -v apt-get >/dev/null 2>&1; then
        echo "Installing Python 3 via apt-get..."
        $SUDO apt-get update && $SUDO apt-get install -y python3
    # Fedora / RHEL / CentOS
    elif command -v dnf >/dev/null 2>&1; then
        echo "Installing Python 3 via dnf..."
        $SUDO dnf install -y python3
    elif command -v yum >/dev/null 2>&1; then
        echo "Installing Python 3 via yum..."
        $SUDO yum install -y python3
    # Arch Linux / Manjaro
    elif command -v pacman >/dev/null 2>&1; then
        echo "Installing Python 3 via pacman..."
        $SUDO pacman -Sy --noconfirm python
    # openSUSE
    elif command -v zypper >/dev/null 2>&1; then
        echo "Installing Python 3 via zypper..."
        $SUDO zypper --non-interactive install python3
    # Alpine Linux
    elif command -v apk >/dev/null 2>&1; then
        echo "Installing Python 3 via apk..."
        $SUDO apk add --no-cache python3
    fi

    PYTHON_BIN=$(find_python || true)

    if [ -z "$PYTHON_BIN" ]; then
        echo ""
        echo "Error: Could not automatically install Python 3."
        echo "Please install Python 3 manually using your distribution's package manager."
        exit 1
    fi
fi

echo "Starting Pura Services with $PYTHON_BIN..."
exec "$PYTHON_BIN" server.py "$@"
