# Schema Exploration Features

## Current state
- **Preset mode**: Curated SQL with JOINs per module/entity
- **Custom mode**: Raw SQL textarea

## Planned additions

### 1. Validate Query (sync action)
Run the user's custom SQL query with a row limit and return column names + sample rows.
Helps the user verify their query before running the full extraction.

- Wraps query in `SELECT * FROM ({query}) WHERE ROWNUM <= 10`
- Returns as sync action result: column names + sample data
- Triggered from a button in the custom SQL section of configRowSchema

### 2. List Tables (sync action)
For a selected module, query `all_tables` to show available EBS tables.

```sql
SELECT table_name FROM all_tables
WHERE owner = 'APPS' AND table_name LIKE '{MODULE_PREFIX}%'
ORDER BY table_name
```

- Helps users discover tables without needing a DBA
- Shows table names as a dropdown or list
- Could also show row counts for small tables

### 3. Presets remain the primary mode
- Curated JOINs are the main differentiator from generic Oracle DB extractor
- Users who need more flexibility use custom mode + validate query
