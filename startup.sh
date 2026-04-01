#!/bin/bash
set -e

# Install ODBC driver for SQL Server
curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list > /etc/apt/sources.list.d/mssql-release.list
apt-get update
ACCEPT_EULA=Y apt-get install -y msodbcsql18

# Start the server
gunicorn -w 1 -b 0.0.0.0:8000 server:app