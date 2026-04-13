"""Unit tests for EBS presets and configuration (no DB connection needed)."""

from datetime import datetime

import pytest
from keboola.component.exceptions import UserException

from configuration import Configuration, ExtractionMode
from ebs_presets import build_query, get_entity_list, get_module_list, get_preset


class TestModuleList:
    def test_returns_all_modules(self) -> None:
        modules = get_module_list()
        keys = {m["value"] for m in modules}
        assert {"ap", "ar", "gl", "po", "inv", "hr", "om", "tca"} == keys

    def test_each_module_has_label(self) -> None:
        for m in get_module_list():
            assert m["label"]
            assert m["value"]


class TestEntityList:
    def test_ap_entities(self) -> None:
        entities = get_entity_list("ap")
        keys = {e["value"] for e in entities}
        assert "ap_invoices" in keys
        assert "ap_invoice_lines" in keys

    def test_gl_entities(self) -> None:
        entities = get_entity_list("gl")
        keys = {e["value"] for e in entities}
        assert "gl_journal_lines" in keys
        assert "gl_balances" in keys

    def test_unknown_module_returns_empty(self) -> None:
        assert get_entity_list("nonexistent") == []


class TestGetPreset:
    def test_known_preset(self) -> None:
        preset = get_preset("ap", "ap_invoices")
        assert preset is not None
        assert preset["name"] == "AP Invoices"
        assert preset["incremental_column"] == "LAST_UPDATE_DATE"

    def test_unknown_preset_returns_none(self) -> None:
        assert get_preset("ap", "nonexistent") is None


class TestBuildQuery:
    def test_multi_org_with_org_id(self) -> None:
        preset = get_preset("ap", "ap_invoices")
        sql, params = build_query(preset, org_id=204)
        assert "org_id = :org_id" in sql
        assert params["org_id"] == 204

    def test_multi_org_without_org_id(self) -> None:
        preset = get_preset("ap", "ap_invoices")
        sql, params = build_query(preset, org_id=None)
        assert ":org_id" not in sql
        assert "org_id" not in params

    def test_ledger_query(self) -> None:
        preset = get_preset("gl", "gl_journal_lines")
        sql, params = build_query(preset, ledger_id=1)
        assert "ledger_id = :ledger_id" in sql
        assert params["ledger_id"] == 1

    def test_incremental_with_since(self) -> None:
        preset = get_preset("ap", "ap_invoices")
        since = datetime(2026, 1, 1)
        sql, params = build_query(preset, org_id=204, since_dt=since)
        assert "LAST_UPDATE_DATE > :since" in sql
        assert params["since"] == since

    def test_snapshot_table_ignores_since(self) -> None:
        preset = get_preset("gl", "gl_balances")
        assert preset["incremental_column"] is None
        sql, params = build_query(preset, ledger_id=1, since_dt=datetime(2026, 1, 1))
        assert ":since" not in sql
        assert "since" not in params

    def test_no_filters_returns_base_query(self) -> None:
        preset = get_preset("tca", "hz_parties")
        sql, params = build_query(preset)
        assert params == {}
        assert "WHERE q." not in sql  # no outer WHERE wrapping


class TestConfiguration:
    def test_flatten_connection(self) -> None:
        cfg = Configuration(
            **{
                "connection": {
                    "db_host": "localhost",
                    "db_port": 1521,
                    "db_service_name": "EBSDB",
                    "#db_user": "user",
                    "#db_password": "pass",
                },
                "source": {"extraction_mode": "preset", "module": "ap", "entity": "ap_invoices"},
                "destination": {"output_table": "test"},
            }
        )
        assert cfg.db_host == "localhost"
        assert cfg.db_user == "user"
        assert cfg.db_password == "pass"

    def test_defaults(self) -> None:
        cfg = Configuration()
        assert cfg.db_host == ""
        assert cfg.db_port == 1521
        assert cfg.source.extraction_mode == ExtractionMode.PRESET
        assert cfg.destination.incremental is False

    def test_validate_row_preset_missing_module(self) -> None:
        cfg = Configuration(
            **{
                "connection": {
                    "db_host": "h",
                    "db_service_name": "s",
                    "#db_user": "u",
                    "#db_password": "p",
                },
                "source": {"extraction_mode": "preset", "module": "", "entity": ""},
                "destination": {"output_table": "t"},
            }
        )
        with pytest.raises(UserException, match="module"):
            cfg.validate_row()

    def test_validate_row_custom_missing_query(self) -> None:
        cfg = Configuration(
            **{
                "connection": {
                    "db_host": "h",
                    "db_service_name": "s",
                    "#db_user": "u",
                    "#db_password": "p",
                },
                "source": {"extraction_mode": "custom", "custom_query": ""},
                "destination": {"output_table": "t"},
            }
        )
        with pytest.raises(UserException, match="custom_query"):
            cfg.validate_row()

    def test_validate_connection_missing_host(self) -> None:
        cfg = Configuration()
        with pytest.raises(UserException, match="db_host"):
            cfg.validate_connection()
