# Future: Explorer Mode (DB Drill-Down)

## Current state
- **Preset mode**: Curated SQL with JOINs per module/entity. Static entity list from ebs_presets.py. Quick start, but limited to what we coded.
- **Custom mode**: Raw SQL textarea. Full flexibility, but user needs to know EBS schema.

## Proposed: Explorer mode (third option)
Cascading DB drill-down that queries the live DB at each step:

```
extraction_mode: [preset | explorer | custom]

Explorer flow:
1. listModules → query fnd_product_installations → show only installed modules
2. listTables(module) → query all_tables WHERE owner='APPS' AND table_name LIKE '{MODULE}_%' 
3. listColumns(table) → query all_tab_columns → user picks columns
4. Component generates: SELECT col1, col2, ... FROM apps.{table} WHERE org_id = :org_id
```

## Differentiator from generic Oracle DB Extractor
- Module grouping (AP, GL, AR tables grouped)
- Auto-detects multi-org tables (_ALL suffix) → adds org_id filter
- Auto-detects incremental column (last_update_date) → enables incremental
- Auto-detects date-effective tables (_F suffix) → adds SYSDATE filter
- Suggested JOINs: when user picks AP_INVOICES_ALL, suggest "include supplier name?" → adds LEFT JOIN

## UI schema changes needed
- `extraction_mode` enum: add "explorer" 
- New async fields: `table` (depends on module), `columns` (multi-select, depends on table)
- Dependencies: explorer fields visible only in explorer mode

## Implementation
- `oracle_client.py`: add `list_module_tables(module)`, `list_table_columns(table)` 
- `component.py`: add `listTables`, `listColumns` sync actions
- `component.py`: add `_run_explorer()` that generates SELECT from picked columns
- `ebs_presets.py`: add metadata about table patterns (multi_org, incremental_column, date_effective)

## Also fix
- `listModules` should query DB (fnd_product_installations) even in preset mode — don't show uninstalled modules
