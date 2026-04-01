#!/bin/bash
set -e

echo "Installing ODBC Driver 18..."

# Get Ubuntu version - try multiple methods
if [ -f /etc/os-release ]; then
    . /etc/os-release
    # Try to get the codename (jammy, noble, etc) or fallback to 22.04
    UBUNTU_VERSION=${UBUNTU_CODENAME:-}
    if [ -z "$UBUNTU_VERSION" ]; then
        # Fallback: detect version from VERSION_ID and map it
        case ${VERSION_ID} in
            20.04) UBUNTU_VERSION="20.04" ;;
            22.04) UBUNTU_VERSION="22.04" ;;
            24.04) UBUNTU_VERSION="24.04" ;;
            *) UBUNTU_VERSION="22.04" ;;  # Default fallback
        esac
    fi
fi

echo "Using Ubuntu version: $UBUNTU_VERSION"

# Add Microsoft repo key
curl -s https://packages.microsoft.com/keys/microsoft.asc | apt-key add - 2>/dev/null || true

# Add Microsoft SQL Server ODBC driver repository
curl -s "https://packages.microsoft.com/config/ubuntu/${UBUNTU_VERSION}/prod.list" | tee /etc/apt/sources.list.d/mssql-release.list > /dev/null

# Update and install ODBC driver
apt-get update
ACCEPT_EULA=Y apt-get install -y msodbcsql18

echo "Starting MCP server..."
gunicorn -w 1 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 server:app