import logging

import oracledb
from keboola.component.exceptions import UserException

FETCH_SIZE = 5000


class OracleEBSClient:
    def __init__(self, host: str, port: int, service_name: str, user: str, password: str) -> None:
        self.dsn = f"{host}:{port}/{service_name}"
        self.user = user
        self.password = password

    def _connect(self) -> oracledb.Connection:
        try:
            return oracledb.connect(user=self.user, password=self.password, dsn=self.dsn)
        except oracledb.DatabaseError as e:
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

    def execute_query(
        self, query: str, params: dict | None = None, fetch_size: int = FETCH_SIZE
    ) -> tuple[list[str], list[dict]]:
        """Execute a query and return (column_names, rows) using fetchmany streaming."""
        logging.debug("Executing query: %s", query[:200])
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.arraysize = fetch_size
                    cur.execute(query, parameters=params or {})
                    columns = [desc[0].upper() for desc in cur.description]
                    all_rows: list[dict] = []
                    while True:
                        batch = cur.fetchmany(fetch_size)
                        if not batch:
                            break
                        for raw_row in batch:
                            all_rows.append(dict(zip(columns, raw_row, strict=False)))
                    logging.info("Query returned %d rows, %d columns", len(all_rows), len(columns))
                    return columns, all_rows
        except oracledb.DatabaseError as e:
            raise UserException(f"Oracle query failed: {e}") from e
