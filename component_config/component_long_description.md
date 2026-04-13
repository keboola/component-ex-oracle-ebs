Oracle E-Business Suite (EBS) extractor connects directly to the Oracle database underlying your EBS instance and extracts data from standard EBS tables.

**Two extraction modes:**

- **Preset mode** — select an EBS module (AP, AR, GL, PO, INV, HR, OM, TCA) and entity from a dropdown. The component generates optimized SQL with proper JOINs (e.g., AP Invoices joined with Supplier names).
- **Custom SQL mode** — write any SELECT query against the EBS database for full flexibility.

**Features:**

- Incremental loading via `LAST_UPDATE_DATE` columns
- Multi-org filtering via Operating Unit (org_id) picker
- GL Ledger picker for General Ledger queries
- 18 pre-built entity queries across 8 EBS modules
- Uses `oracledb` thin driver — no Oracle client installation required

**Supported modules:** Accounts Payable, Accounts Receivable, General Ledger, Purchasing, Inventory, Human Resources, Order Management, Trading Community Architecture (Customers).
