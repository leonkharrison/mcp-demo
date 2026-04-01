#!/bin/bash
set -e

# Install ODBC driver for SQL Server
echo "Installing ODBC Driver 18..."

# Get Ubuntu version from /etc/os-release
. /etc/os-release
UBUNTU_VERSION_ID=$VERSION_ID

echo "Detected Ubuntu version: $UBUNTU_VERSION_ID"

# Add Microsoft repo key
curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - 2>/dev/null || true

# Add Microsoft SQL Server ODBC driver repository
curl "https://packages.microsoft.com/config/ubuntu/${UBUNTU_VERSION_ID}/prod.list" > /etc/apt/sources.list.d/mssql-release.list

# Update and install ODBC driver
apt-get update
ACCEPT_EULA=Y apt-get install -y msodbcsql18

echo "Starting MCP server..."
gunicorn -w 1 -b 0.0.0.0:8000 server:app