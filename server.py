import os
import re
import pyodbc
from contextlib import asynccontextmanager
from dataclasses import dataclass
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()


# Global connection string
connection_string = None

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _build_connection_string() -> str:
    server = os.environ["SQL_SERVER"]
    database = os.environ["SQL_DATABASE"]
    username = os.environ["SQL_USERNAME"]
    password = os.environ["SQL_PASSWORD"]
    conn_string = os.getenv("CONN_STRING")
    if conn_string:
        return conn_string
    driver = "ODBC Driver 18 for SQL Server"
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    global connection_string
    connection_string = _build_connection_string()
    # Validate connectivity at startup — fail fast before any client connects
    conn = pyodbc.connect(connection_string, timeout=10)
    conn.close()
    yield


# ---------------------------------------------------------------------------
# SELECT-only enforcement
# ---------------------------------------------------------------------------

_SELECT_ONLY_RE = re.compile(
    r"^\s*(?:--[^\n]*\n\s*)*SELECT\b",
    re.IGNORECASE,
)

_BLOCKED_KEYWORDS_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|CREATE|ALTER|EXEC|EXECUTE|"
    r"sp_|xp_|OPENROWSET|OPENDATASOURCE|BULK|GRANT|REVOKE|DENY)\b",
    re.IGNORECASE,
)


def _validate_select_query(query: str) -> None:
    """Raise ValueError if the query is not a safe SELECT statement."""
    stripped = query.strip()
    if not stripped:
        raise ValueError("Query cannot be empty.")
    if not _SELECT_ONLY_RE.match(stripped):
        raise ValueError(
            "Only SELECT queries are permitted. The query must begin with SELECT."
        )
    if _BLOCKED_KEYWORDS_RE.search(stripped):
        raise ValueError(
            "Query contains a prohibited keyword. "
            "Only read-only SELECT statements are allowed."
        )


# ---------------------------------------------------------------------------
# MCP server and tools
# ---------------------------------------------------------------------------

mcp = FastMCP("AdventureWorks SQL Server", lifespan=app_lifespan)


@mcp.tool()
def list_tables() -> list[dict]:
    """
    List all user tables in the AdventureWorks database.

    Returns each table's schema name, table name, and approximate row count.
    Use this to discover what data is available before querying or fetching schemas.
    """
    query = """
        SELECT
            s.name  AS schema_name,
            t.name  AS table_name,
            p.rows  AS row_count
        FROM sys.tables t
        JOIN sys.schemas    s ON t.schema_id  = s.schema_id
        JOIN sys.partitions p ON t.object_id  = p.object_id
                              AND p.index_id IN (0, 1)
        ORDER BY s.name, t.name
    """
    with pyodbc.connect(connection_string, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


@mcp.tool()
def get_schema(table_name: str, schema_name: str = "dbo") -> list[dict]:
    """
    Get the column definitions for a specific table.

    Returns column name, data type, max length, nullability, and whether
    each column is a primary key or foreign key.

    Args:
        table_name:  The table name, e.g. "SalesOrderHeader"
        schema_name: The schema name (default: "dbo"), e.g. "Sales"
    """
    query = """
        SELECT
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.CHARACTER_MAXIMUM_LENGTH,
            c.IS_NULLABLE,
            CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 'YES' ELSE 'NO' END AS IS_PRIMARY_KEY,
            CASE WHEN fk.COLUMN_NAME IS NOT NULL THEN 'YES' ELSE 'NO' END AS IS_FOREIGN_KEY
        FROM INFORMATION_SCHEMA.COLUMNS c
        LEFT JOIN (
            SELECT ku.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
              ON  tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
              AND tc.TABLE_SCHEMA    = ku.TABLE_SCHEMA
            WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
              AND ku.TABLE_NAME      = ?
              AND ku.TABLE_SCHEMA    = ?
        ) pk ON c.COLUMN_NAME = pk.COLUMN_NAME
        LEFT JOIN (
            SELECT ku.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
              ON  tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
              AND tc.TABLE_SCHEMA    = ku.TABLE_SCHEMA
            WHERE tc.CONSTRAINT_TYPE = 'FOREIGN KEY'
              AND ku.TABLE_NAME      = ?
              AND ku.TABLE_SCHEMA    = ?
        ) fk ON c.COLUMN_NAME = fk.COLUMN_NAME
        WHERE c.TABLE_NAME   = ?
          AND c.TABLE_SCHEMA = ?
        ORDER BY c.ORDINAL_POSITION
    """
    with pyodbc.connect(connection_string, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute(
            query,
            table_name, schema_name,  # pk subquery
            table_name, schema_name,  # fk subquery
            table_name, schema_name,  # WHERE clause
        )
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    if not rows:
        raise ValueError(
            f"Table '{schema_name}.{table_name}' not found. "
            "Use list_tables() to see available tables."
        )
    return rows


@mcp.tool()
def execute_query(query: str, max_rows: int = 100) -> dict:
    """
    Execute a SELECT query against the AdventureWorks database.

    Only SELECT statements are permitted — any attempt to run INSERT, UPDATE,
    DELETE, DROP, or other write/DDL operations will be rejected.

    Args:
        query:    A SQL SELECT statement to execute.
        max_rows: Maximum rows to return (default 100, capped at 1000).

    Returns a dict with:
        columns:   List of column names
        rows:      List of row dicts
        row_count: Number of rows returned
        truncated: True if results were cut off at max_rows
    """
    max_rows = min(max(1, max_rows), 1000)

    _validate_select_query(query)

    with pyodbc.connect(connection_string, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        rows = []
        truncated = False
        for i, row in enumerate(cursor):
            if i >= max_rows:
                truncated = True
                break
            rows.append(dict(zip(columns, row)))

    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# Expose the ASGI app for uvicorn: `uvicorn server:app` (used by Azure App Service)
app = mcp.streamable_http_app()

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8000"))

    if transport == "streamable-http":
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        mcp.run(transport="stdio")
