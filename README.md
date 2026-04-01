# AdventureWorks MCP Server

A Python MCP server that lets any MCP-compatible AI client query the AdventureWorks Azure SQL Database using plain English. The AI calls the tools below; you only need to configure the connection once.

## Tools

| Tool | Description |
|---|---|
| `list_tables` | List all tables with schema and row count |
| `get_schema` | Get columns, types, PK/FK info for a table |
| `execute_query` | Run a SELECT query (writes blocked) |

---

## Prerequisites

- Python 3.11+
- [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- Access to an Azure SQL Database with AdventureWorks

---

## Local Setup

```bash
# 1. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure credentials
cp .env.example .env
# Edit .env and fill in your SQL_SERVER, SQL_DATABASE, SQL_USERNAME, SQL_PASSWORD
```

---

## Running Locally (stdio)

The default transport is `stdio`, which is used by Claude Desktop, Claude Code, and GitHub Copilot when they launch the server as a subprocess.

```bash
python server.py
```

### Test with MCP Inspector

```bash
npx @modelcontextprotocol/inspector python server.py
```

Open the inspector URL, then try:
- `list_tables` — no arguments
- `get_schema` — `table_name: "SalesOrderHeader"`, `schema_name: "Sales"`
- `execute_query` — `query: "SELECT TOP 5 * FROM Sales.SalesOrderHeader"`
- `execute_query` — `query: "DROP TABLE foo"` → should return an error

---

## Running as HTTP Server

Set `MCP_TRANSPORT=streamable-http` in `.env` (or as an environment variable), then:

```bash
python server.py
# Server listens on http://127.0.0.1:8000/mcp
```

---

## Client Configuration

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "adventureworks": {
      "command": "python",
      "args": ["/Users/leon.k.harrison/Claude/Python/server.py"],
      "env": {
        "SQL_SERVER": "your-server.database.windows.net",
        "SQL_DATABASE": "AdventureWorks",
        "SQL_USERNAME": "your-username",
        "SQL_PASSWORD": "your-password"
      }
    }
  }
}
```

Restart Claude Desktop after saving.

### Claude Code

Add a `.mcp.json` file in this directory:

```json
{
  "mcpServers": {
    "adventureworks": {
      "command": "python",
      "args": ["server.py"]
    }
  }
}
```

Set credentials in your shell environment or in `.env`. Claude Code picks up `.mcp.json` automatically when you open a project in this directory.

Or add via CLI:
```bash
claude mcp add adventureworks -- python /Users/leon.k.harrison/Claude/Python/server.py
```

### GitHub Copilot (VS Code)

Add to `.vscode/settings.json` in your workspace:

```json
{
  "github.copilot.chat.mcp.servers": {
    "adventureworks": {
      "command": "python",
      "args": ["${workspaceFolder}/server.py"],
      "env": {
        "SQL_SERVER": "your-server.database.windows.net",
        "SQL_DATABASE": "AdventureWorks",
        "SQL_USERNAME": "your-username",
        "SQL_PASSWORD": "your-password"
      }
    }
  }
}
```

### Any Client (Azure HTTP deployment)

```
https://your-app.azurewebsites.net/mcp
```

---

## Azure App Service Deployment

### Application Settings (replace your `.env`)

| Key | Value |
|---|---|
| `SQL_SERVER` | `your-server.database.windows.net` |
| `SQL_DATABASE` | `AdventureWorks` |
| `SQL_USERNAME` | `your-username` |
| `SQL_PASSWORD` | `your-password` |
| `MCP_TRANSPORT` | `streamable-http` |
| `WEBSITES_PORT` | `8000` |

### Startup Command

The `startup.txt` file in this repo is picked up automatically by Azure App Service on Linux. It runs:

```
gunicorn -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 server:app
```

Alternatively, set this as the startup command manually in **Configuration > General settings**.

### Additional hardening (recommended)

- Create a dedicated SQL login with only the `db_datareader` role on the AdventureWorks database
- Restrict the Azure SQL firewall to the App Service outbound IPs
- Enable Azure App Service authentication (Easy Auth) if you want per-user access control

---

## Security

Write operations are blocked in two ways:

1. **Code-level**: `execute_query` rejects any query that does not start with `SELECT` or that contains prohibited keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `EXEC`, etc.)
2. **Database-level** (recommended): Provision the SQL login with `db_datareader` only, so even if the code check were bypassed, the database would reject write operations
