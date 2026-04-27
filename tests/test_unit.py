"""Unit tests for EBS presets and configuration (no DB connection needed)."""

from datetime import datetime
from unittest import mock

import pytest
from keboola.component.exceptions import UserException

from configuration import Configuration, ExtractionMode, SSHOptions
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
        assert preset is not None
        sql, params = build_query(preset, org_id=204)
        assert "org_id = :org_id" in sql
        assert params["org_id"] == 204

    def test_multi_org_without_org_id(self) -> None:
        preset = get_preset("ap", "ap_invoices")
        assert preset is not None
        sql, params = build_query(preset, org_id=None)
        assert ":org_id" not in sql
        assert "org_id" not in params

    def test_ledger_query(self) -> None:
        preset = get_preset("gl", "gl_journal_lines")
        assert preset is not None
        sql, params = build_query(preset, ledger_id=1)
        assert "ledger_id = :ledger_id" in sql
        assert params["ledger_id"] == 1

    def test_incremental_with_since(self) -> None:
        preset = get_preset("ap", "ap_invoices")
        assert preset is not None
        since = datetime(2026, 1, 1)
        sql, params = build_query(preset, org_id=204, since_dt=since)
        assert "LAST_UPDATE_DATE > :since" in sql
        assert params["since"] == since

    def test_snapshot_table_ignores_since(self) -> None:
        preset = get_preset("gl", "gl_balances")
        assert preset is not None
        assert preset["incremental_column"] is None
        sql, params = build_query(preset, ledger_id=1, since_dt=datetime(2026, 1, 1))
        assert ":since" not in sql
        assert "since" not in params

    def test_no_filters_returns_base_query(self) -> None:
        preset = get_preset("tca", "hz_parties")
        assert preset is not None
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
                    "db_user": "user",
                    "#db_password": "pass",
                },
                "source": {"extraction_mode": "Preset", "module": "ap", "entity": "ap_invoices"},
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
                    "db_user": "u",
                    "#db_password": "p",
                },
                "source": {"extraction_mode": "Preset", "module": "", "entity": ""},
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
                    "db_user": "u",
                    "#db_password": "p",
                },
                "source": {"extraction_mode": "Custom", "custom_query": ""},
                "destination": {"output_table": "t"},
            }
        )
        with pytest.raises(UserException, match="custom_query"):
            cfg.validate_row()

    def test_validate_connection_missing_host(self) -> None:
        cfg = Configuration()
        with pytest.raises(UserException, match="db_host"):
            cfg.validate_connection()


class TestSSHOptions:
    def test_default_disabled(self) -> None:
        cfg = Configuration()
        assert cfg.ssh_options.enabled is False
        assert cfg.ssh_options.ssh_port == 22
        assert cfg.ssh_options.keys.private == ""

    def test_parses_platform_aliases(self) -> None:
        cfg = Configuration(
            **{
                "connection": {"db_host": "db", "db_service_name": "s", "db_user": "u", "#db_password": "p"},
                "ssh_options": {
                    "enabled": True,
                    "user": "tunnel",
                    "sshHost": "bastion",
                    "sshPort": 2222,
                    "keys": {"#private": "PRIV", "public": "PUB"},
                },
            }
        )
        assert cfg.ssh_options.enabled is True
        assert cfg.ssh_options.ssh_host == "bastion"
        assert cfg.ssh_options.ssh_port == 2222
        assert cfg.ssh_options.user == "tunnel"
        assert cfg.ssh_options.keys.private == "PRIV"
        assert cfg.ssh_options.keys.public == "PUB"


class _FakeTunnel:
    """Stand-in for sshtunnel.SSHTunnelForwarder."""

    instances: list["_FakeTunnel"] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.is_active = False
        self.local_bind_port = 1521
        self.start_calls = 0
        self.stop_calls = 0
        _FakeTunnel.instances.append(self)

    def start(self) -> None:
        self.start_calls += 1
        self.is_active = True

    def stop(self) -> None:
        self.stop_calls += 1
        self.is_active = False


class TestComponentSSHTunnel:
    """Verify Component._build_client wires the SSH tunnel correctly without a real bastion."""

    def _make_component(self, ssh_enabled: bool):
        # Construct Component bypassing ComponentBase.__init__ so we don't need data dir.
        from component import Component  # local import to avoid loading at module import

        comp = Component.__new__(Component)
        comp.params = Configuration(
            **{
                "connection": {
                    "db_host": "remote-db",
                    "db_port": 1521,
                    "db_service_name": "EBSDB",
                    "db_user": "u",
                    "#db_password": "p",
                },
                "ssh_options": {
                    "enabled": ssh_enabled,
                    "user": "tunnel",
                    "sshHost": "bastion",
                    "sshPort": 22,
                    "keys": {"#private": "PRIV"},
                },
            }
        )
        comp._ssh_tunnel = None
        return comp

    def test_disabled_ssh_uses_remote_host(self) -> None:
        _FakeTunnel.instances.clear()
        comp = self._make_component(ssh_enabled=False)
        with mock.patch("component.SSHTunnelForwarder", _FakeTunnel):
            client = comp._build_client()
        assert client.dsn == "remote-db:1521/EBSDB"
        assert _FakeTunnel.instances == []

    def test_enabled_ssh_rewrites_to_localhost(self) -> None:
        _FakeTunnel.instances.clear()
        comp = self._make_component(ssh_enabled=True)
        with (
            mock.patch("component.SSHTunnelForwarder", _FakeTunnel),
            mock.patch("component.get_private_key", return_value=mock.Mock()),
        ):
            client = comp._build_client()
        assert client.dsn == "127.0.0.1:1521/EBSDB"
        assert len(_FakeTunnel.instances) == 1
        assert _FakeTunnel.instances[0].start_calls == 1

    def test_ensure_ssh_tunnel_is_idempotent(self) -> None:
        _FakeTunnel.instances.clear()
        comp = self._make_component(ssh_enabled=True)
        with (
            mock.patch("component.SSHTunnelForwarder", _FakeTunnel),
            mock.patch("component.get_private_key", return_value=mock.Mock()),
        ):
            comp._build_client()
            comp._build_client()
        assert len(_FakeTunnel.instances) == 1
        assert _FakeTunnel.instances[0].start_calls == 1

    def test_stop_ssh_tunnel_called_on_run_finally(self) -> None:
        _FakeTunnel.instances.clear()
        comp = self._make_component(ssh_enabled=True)
        with (
            mock.patch("component.SSHTunnelForwarder", _FakeTunnel),
            mock.patch("component.get_private_key", return_value=mock.Mock()),
        ):
            comp._build_client()
            comp._stop_ssh_tunnel()
        assert _FakeTunnel.instances[0].stop_calls == 1
        assert _FakeTunnel.instances[0].is_active is False


def test_ssh_options_unused_import() -> None:
    """Smoke test that SSHOptions is importable directly."""
    assert SSHOptions().enabled is False
