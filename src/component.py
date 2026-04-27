"""Oracle E-Business Suite Extractor.

Extracts data from Oracle EBS database tables via direct Oracle DB connection (oracledb thin driver).
Supports preset module/entity selection with pre-built SQL, or custom SQL queries.
"""

import csv
import logging
from datetime import UTC, datetime

from keboola.component.base import ComponentBase, sync_action
from keboola.component.dao import BaseType, ColumnDefinition, SupportedDataTypes
from keboola.component.exceptions import UserException
from keboola.component.sync_actions import SelectElement

from configuration import Configuration, ExtractionMode
from ebs_presets import build_query, get_entity_list, get_preset
from oracle_client import OracleEBSClient


class Component(ComponentBase):
    def __init__(self) -> None:
        super().__init__()
        self.params = Configuration(**self.configuration.parameters)

    def run(self) -> None:
        """Main execution — orchestrates the extraction workflow."""
        self.params.validate_row()
        client = self._build_client()

        if self.params.source.extraction_mode == ExtractionMode.PRESET:
            self._run_preset(client)
        else:
            self._run_custom(client)

    # ── Sync Actions ──────────────────────────────────────────────

    @sync_action("testConnection")
    def test_connection(self) -> None:
        self.params.validate_connection()
        result = self._build_client().test_connection()
        logging.info("Connection OK — %s", result["version"])

    @sync_action("listOperatingUnits")
    def list_operating_units(self) -> list[SelectElement]:
        self.params.validate_connection()
        rows = self._build_client().list_operating_units()
        return [SelectElement(value=str(r["ORGANIZATION_ID"]), label=f"{r['NAME']}") for r in rows]

    @sync_action("listLedgers")
    def list_ledgers(self) -> list[SelectElement]:
        self.params.validate_connection()
        rows = self._build_client().list_ledgers()
        return [SelectElement(value=str(r["LEDGER_ID"]), label=f"{r['NAME']} ({r['CURRENCY_CODE']})") for r in rows]

    @sync_action("listEntities")
    def list_entities(self) -> list[SelectElement]:
        module = self.configuration.parameters.get("source", {}).get("module", "")
        if not module:
            raise UserException("Select a module first, then reload entities.")
        return [SelectElement(value=e["value"], label=e["label"]) for e in get_entity_list(module)]

    @sync_action("listTables")
    def list_tables(self) -> list[SelectElement]:
        """List EBS tables for a module prefix (e.g. AP → AP_INVOICES_ALL, AP_SUPPLIERS, ...)."""
        self.params.validate_connection()
        module = self.configuration.parameters.get("source", {}).get("module", "")
        if not module:
            raise UserException("Select a module first, then reload tables.")
        # Map module keys to Oracle table prefixes
        prefix_map = {
            "ap": "AP_",
            "ar": "RA_",
            "gl": "GL_",
            "po": "PO_",
            "inv": "MTL_",
            "hr": "PER_",
            "om": "OE_",
            "tca": "HZ_",
        }
        prefix = prefix_map.get(module, f"{module.upper()}_")
        rows = self._build_client().list_module_tables(prefix)
        return [SelectElement(value=r["TABLE_NAME"], label=r["TABLE_NAME"]) for r in rows]

    @sync_action("validateQuery")
    def validate_query(self) -> None:
        """Run user's custom SQL with ROWNUM <= 10 and log column names + row count."""
        self.params.validate_connection()
        query = self.configuration.parameters.get("source", {}).get("custom_query", "")
        if not query:
            raise UserException("Enter a SQL query first.")
        columns, rows = self._build_client().validate_query(query)
        logging.info("Query valid — %d columns, %d sample rows", len(columns), len(rows))
        logging.info("Columns: %s", ", ".join(columns))

    # ── Extraction ────────────────────────────────────────────────

    def _run_preset(self, client: OracleEBSClient) -> None:
        src = self.params.source
        dest = self.params.destination

        preset = get_preset(src.module, src.entity)
        if not preset:
            raise UserException(f"Unknown preset: module={src.module!r}, entity={src.entity!r}")

        since_dt = self._get_since_datetime()
        sql, params = build_query(preset, src.org_id, src.ledger_id, since_dt)

        output_table = dest.output_table or preset["default_output_table"]
        pk = dest.primary_key or preset["default_primary_key"]

        logging.info("Preset extraction: %s/%s → %s", src.module, src.entity, output_table)
        columns, rows = client.execute_query(sql, params=params)

        self._write_table(output_table, columns, rows, dest.incremental, pk)

        if dest.incremental and preset.get("incremental_column"):
            self._save_state(output_table)

    def _run_custom(self, client: OracleEBSClient) -> None:
        dest = self.params.destination
        query = self.params.source.custom_query

        logging.info("Custom query → %s", dest.output_table)
        columns, rows = client.execute_query(query)

        self._write_table(dest.output_table, columns, rows, dest.incremental, dest.primary_key)

        if dest.incremental:
            self._save_state(dest.output_table)

    # ── Helpers ───────────────────────────────────────────────────

    def _build_client(self) -> OracleEBSClient:
        p = self.params
        return OracleEBSClient(
            host=p.db_host,
            port=p.db_port,
            service_name=p.db_service_name,
            user=p.db_user,
            password=p.db_password,
        )

    def _get_since_datetime(self) -> datetime | None:
        if not self.params.destination.incremental:
            return None
        state = self.get_state_file()
        output_table = self.params.destination.output_table
        since_str = state.get(output_table, {}).get("last_run")
        if since_str:
            return datetime.fromisoformat(since_str)
        return None

    def _save_state(self, output_table: str) -> None:
        state = self.get_state_file()
        state[output_table] = {"last_run": datetime.now(UTC).isoformat()}
        self.write_state_file(state)

    def _write_table(
        self,
        table_name: str,
        columns: list[str],
        rows: list[dict],
        incremental: bool = False,
        primary_key: list[str] | None = None,
    ) -> None:
        pk = primary_key or []
        columns = _normalize_columns(columns)
        rows = [{_normalize_col_name(k): v for k, v in row.items()} for row in rows]
        pk = [_normalize_col_name(k) for k in pk]

        schema = _build_schema(columns, pk, rows)
        table_def = self.create_out_table_definition(
            f"{table_name}.csv",
            incremental=incremental,
            schema=schema,
            primary_key=pk,
            has_header=True,
        )

        with open(table_def.full_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                # Convert non-string values to strings for CSV
                writer.writerow({k: _to_csv_value(v) for k, v in row.items()})

        self.write_manifest(table_def)
        logging.info("Wrote %d rows to %s", len(rows), table_name)


# ── Standalone utilities ─────────────────────────────────────────


def _normalize_col_name(name: str) -> str:
    """Normalize a column name for Keboola Storage (lowercase, no special chars)."""
    return name.strip().lower().replace(" ", "_")


def _normalize_columns(columns: list[str]) -> list[str]:
    return [_normalize_col_name(c) for c in columns]


def _to_csv_value(value: object) -> str:
    """Convert a value to CSV-safe string."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _build_schema(columns: list[str], primary_key: list[str], rows: list[dict]) -> dict[str, ColumnDefinition]:
    """Infer column types from first non-empty row of data."""
    sample: dict = {}
    if rows:
        sample = rows[0]

    schema: dict[str, ColumnDefinition] = {}
    for col in columns:
        val = sample.get(col)
        is_pk = col in primary_key

        if val is not None and isinstance(val, (int, float)):
            base_type = SupportedDataTypes.NUMERIC
        else:
            base_type = SupportedDataTypes.STRING

        schema[col] = ColumnDefinition(
            data_types=BaseType(dtype=base_type),
            nullable=not is_pk,
        )
    return schema


"""Main entrypoint"""
if __name__ == "__main__":
    try:
        comp = Component()
        comp.execute_action()
    except UserException as exc:
        logging.exception(exc)
        exit(1)
    except Exception as exc:
        logging.exception(exc)
        exit(2)
