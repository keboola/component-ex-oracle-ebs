"""Oracle EBS database client for read (query) operations.

Uses oracledb in thick mode when Oracle Instant Client is available
(required for Oracle EBS servers with `sec_case_sensitive_logon=FALSE` or
legacy 10G password verifiers), otherwise falls back to thin mode.
"""

import logging
import os
from collections.abc import Iterator

import oracledb
from keboola.component.exceptions import UserException

FETCH_SIZE = 5000

# Oracle Instant Client search order. Docker image installs to /opt/oracle/instantclient;
# local dev commonly uses ~/oracle/instantclient_<ver>. Override with ORACLE_CLIENT_LIB_DIR.
_INSTANT_CLIENT_PATHS = [
    os.environ.get("ORACLE_CLIENT_LIB_DIR", ""),
    "/opt/oracle/instantclient",
    os.path.expanduser("~/oracle/instantclient_23_3"),
    os.path.expanduser("~/oracle/instantclient"),
]


def _init_thick_mode_if_available() -> bool:
    """Enable oracledb thick mode if Instant Client is installed. Returns True on success.

    Thick mode is required for Oracle servers using `sec_case_sensitive_logon=FALSE` or
    advertising only the 10G password verifier — both common on older Oracle EBS installs.

    Set env var `ORACLE_THIN_MODE_ONLY=1` to skip thick-mode init (used by VCR recording
    so the cursor wrapper in keboola-vcr's DB adapter — which is thin-only — keeps working).
    """
    if os.environ.get("ORACLE_THIN_MODE_ONLY") == "1":
        logging.info("ORACLE_THIN_MODE_ONLY=1 set; using thin mode")
        return False

    tried: list[str] = []
    for candidate in _INSTANT_CLIENT_PATHS:
        if not candidate:
            continue
        if not os.path.isdir(candidate):
            continue
        tried.append(candidate)
        try:
            oracledb.init_oracle_client(lib_dir=candidate)
            logging.info("Oracle thick mode enabled: lib_dir=%s", candidate)
            return True
        except oracledb.ProgrammingError:
            # Already initialized — idempotent, still thick mode
            return True
        except Exception as e:
            # Surface the real failure reason so the operator can fix it.
            logging.warning("Failed to init Oracle thick mode with %s: %s", candidate, e)
    if tried:
        logging.warning(
            "Oracle Instant Client directories were present but none loaded: %s. Using thin mode.",
            ", ".join(tried),
        )
    else:
        logging.info("Oracle Instant Client not found; using thin mode")
    return False


# Initialize thick mode at import time — once per process.
_init_thick_mode_if_available()


class OracleEBSClient:
    def __init__(self, host: str, port: int, service_name: str, user: str, password: str) -> None:
        self.dsn = f"{host}:{port}/{service_name}"
        self.user = user
        self.password = password

    def _connect(self) -> oracledb.Connection:
        try:
            return oracledb.connect(
                user=self.user,
                password=self.password,
                dsn=self.dsn,
                tcp_connect_timeout=30,
            )
        except oracledb.Error as e:
            msg = str(e)
            if "DPY-3015" in msg:
                raise UserException(
                    f"Cannot connect to Oracle EBS at {self.dsn}: the user '{self.user}' has only "
                    f"the legacy 10G password verifier and the bundled Oracle Instant Client failed "
                    f"to load (falling back to thin mode). Ask your DBA to either:\n"
                    f"  1. Reset the password so 11G/12C verifiers are generated:\n"
                    f"     ALTER USER {self.user} IDENTIFIED BY <same-or-new-password>;\n"
                    f"  2. Ensure sec_case_sensitive_logon is TRUE at the DB/PDB level.\n"
                    f"Original error: {e}"
                ) from e
            raise UserException(f"Cannot connect to Oracle EBS at {self.dsn}: {e}") from e

    def test_connection(self) -> dict[str, str]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT banner FROM v$version WHERE ROWNUM = 1")
                row = cur.fetchone()
                return {"version": row[0] if row else "unknown", "dsn": self.dsn}

    def list_operating_units(self) -> list[dict]:
        sql = """
            SELECT organization_id, name
            FROM apps.hr_operating_units
            ORDER BY name
        """
        _cols, rows = self.execute_query(sql)
        return rows

    def list_ledgers(self) -> list[dict]:
        sql = """
            SELECT ledger_id, name, short_name, currency_code
            FROM apps.gl_ledgers
            WHERE ledger_category_code = 'PRIMARY'
            ORDER BY name
        """
        _cols, rows = self.execute_query(sql)
        return rows

    def list_module_tables(self, module_prefix: str) -> list[dict]:
        sql = """
            SELECT table_name
            FROM all_tables
            WHERE owner = 'APPS' AND table_name LIKE :prefix
            ORDER BY table_name
        """
        _cols, rows = self.execute_query(sql, params={"prefix": f"{module_prefix.upper()}%"})
        return rows

    def validate_query(self, query: str) -> tuple[list[str], list[dict]]:
        """Run a query with ROWNUM <= 10 limit and return columns + sample rows."""
        limited = f"SELECT * FROM ({query.strip().rstrip(';').strip()}) WHERE ROWNUM <= 10"
        return self.execute_query(limited)

    def get_table_columns(self, table_name: str) -> list[dict]:
        parts = table_name.upper().split(".")
        owner = parts[0] if len(parts) > 1 else "APPS"
        tname = parts[-1]
        sql = """
            SELECT column_name, data_type, nullable
            FROM all_tab_columns
            WHERE owner = :owner AND table_name = :table_name
            ORDER BY column_id
        """
        _cols, rows = self.execute_query(sql, params={"owner": owner, "table_name": tname})
        return rows

    def execute_query_stream(
        self, query: str, params: dict | None = None, fetch_size: int = FETCH_SIZE
    ) -> tuple[list[str], Iterator[dict]]:
        """Execute a query and return (column_names, generator yielding row dicts).

        The generator owns the cursor and connection — it closes both when exhausted,
        garbage-collected, or closed by the caller. Lets large result sets stream to
        disk without buffering the whole table in memory.
        """
        query = query.strip().rstrip(";").strip()
        logging.debug("Executing query: %s", query[:200])
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.arraysize = fetch_size
            cur.execute(query, parameters=params or {})
            description = cur.description or []
            columns = [desc[0].upper() for desc in description]
        except oracledb.Error as e:
            raise UserException(f"Oracle query failed: {e}") from e

        def _row_iter() -> Iterator[dict]:
            row_count = 0
            try:
                while True:
                    batch = cur.fetchmany(fetch_size)
                    if not batch:
                        break
                    for raw_row in batch:
                        yield dict(zip(columns, raw_row, strict=False))
                    row_count += len(batch)
                logging.info("Query returned %d rows, %d columns", row_count, len(columns))
            except oracledb.Error as e:
                raise UserException(f"Oracle query failed: {e}") from e
            finally:
                try:
                    cur.close()
                finally:
                    conn.close()

        return columns, _row_iter()

    def execute_query(
        self, query: str, params: dict | None = None, fetch_size: int = FETCH_SIZE
    ) -> tuple[list[str], list[dict]]:
        """Execute a query and return (column_names, rows) materialized as a list.

        Convenience wrapper around `execute_query_stream` for callers that need
        the full result set in memory (sync actions, small lookups). Don't use
        for the main extraction path — prefer streaming.
        """
        columns, rows_iter = self.execute_query_stream(query, params, fetch_size)
        return columns, list(rows_iter)
