# Oracle E-Business Suite Extractor

Extract data from Oracle E-Business Suite via direct database connection using the `oracledb` driver.

## Requirements

The component ships with Oracle Instant Client Basic Light (~50 MB) embedded in the Docker image so it connects out of the box against any supported Oracle EBS version — including older installations that only advertise the legacy 10G password verifier or run with `sec_case_sensitive_logon = FALSE`. No Oracle client installation is required on customer infrastructure; the component speaks to the EBS database directly.

Internally, `python-oracledb` runs in **thick mode** when the bundled Instant Client is loadable, and falls back to **thin mode** otherwise. Thick mode transparently handles the full range of Oracle authentication protocols (10G, 11G, 12C).

Oracle Instant Client is distributed under the [Oracle Free Use Terms and Conditions (FUTC)](https://www.oracle.com/downloads/licenses/oracle-free-license.html) and is freely redistributable in third-party applications.

## Features

| Feature | Description |
|---|---|
| Preset Mode | Select EBS module and entity from dropdowns — component generates optimized SQL with JOINs |
| Custom SQL Mode | Write any SELECT query for full flexibility |
| Incremental Loading | Delta extraction via `LAST_UPDATE_DATE` columns |
| Multi-Org Filtering | Operating Unit picker for `org_id` filtering |
| GL Ledger Picker | Ledger selection for General Ledger queries |
| Sync Actions | Test connection, list operating units, list ledgers, list modules, list entities |

## Supported EBS Modules

- **AP** — Accounts Payable (invoices, lines, payments, suppliers)
- **AR** — Accounts Receivable (invoices, receipts)
- **GL** — General Ledger (journal lines, balances, chart of accounts)
- **PO** — Purchasing (headers, lines)
- **INV** — Inventory (transactions, items)
- **HR** — Human Resources (employees)
- **OM** — Order Management (order headers, lines)
- **TCA** — Trading Community Architecture (parties, customer accounts)

## Configuration

### Connection Settings (configSchema)

| Parameter | Description |
|---|---|
| `db_host` | Oracle database server hostname or IP |
| `db_port` | Port (default: 1521) |
| `db_service_name` | Oracle service name (e.g. `ebs_EBSDB`) |
| `db_user` | Database username |
| `#db_password` | Database password (encrypted) |

### Extraction Row (configRowSchema)

| Parameter | Description |
|---|---|
| `extraction_mode` | `preset` (guided) or `custom` (raw SQL) |
| `module` | EBS module code (preset mode) |
| `entity` | Entity within module (preset mode) |
| `org_id` | Operating Unit ID for multi-org tables |
| `ledger_id` | Ledger ID for GL queries |
| `custom_query` | SQL SELECT statement (custom mode) |
| `output_table` | Target table name in Keboola Storage |
| `incremental` | Enable incremental loading |
| `primary_key` | Primary key columns |

## Development

```bash
git clone https://github.com/keboola/component-ex-oracle-ebs
cd component-ex-oracle-ebs
docker-compose build
docker-compose run --rm dev
```

### Run tests

```bash
docker-compose run --rm test
```

### Record functional test cassettes

Requires a running Oracle EBS instance and `tests/setup/secrets.json` with real credentials:

```bash
uv run python -m keboola.datadirtest scaffold --secrets tests/setup/secrets.json
```

## Deployment

See [Keboola Developer Documentation](https://developers.keboola.com/extend/component/deployment/).
