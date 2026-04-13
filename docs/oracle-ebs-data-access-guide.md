# Oracle E-Business Suite - Data Access Guide (Tested)

How to read and write data in Oracle EBS 12.2. All examples tested against Vision Demo instance on 2026-04-12.

---

## Connecting to the Test Environment

### Prerequisites

Add this line to your local `/etc/hosts` (required - EBS redirects use this hostname):

```
34.140.79.124 apps.example.com
```

On Mac/Linux:
```bash
sudo sh -c 'echo "34.140.79.124 apps.example.com" >> /etc/hosts'
```

> **Note:** IP address changes on VM restart. Check current IP:
> ```bash
> gcloud compute instances describe oracle-ebs-appliance --zone=europe-west1-b --project=components-factory-dev --format="value(networkInterfaces[0].accessConfigs[0].natIP)"
> ```

### Connection Details

| What | Value |
|------|-------|
| **Web UI** | http://apps.example.com:8000/OA_HTML/AppsLocalLogin.jsp |
| **EBS Login** | SYSADMIN / manager1 |
| **REST API Base** | http://apps.example.com:8000/webservices/rest/ |
| **REST Auth** | HTTP Basic: SYSADMIN / manager1 |
| **DB Host** | apps.example.com |
| **DB Port** | 1521 |
| **DB Service** | ebs_EBSDB |
| **DB User (internal/EBS)** | apps / apps |
| **DB User (external JDBC)** | keboola_ro / keboola123 (read-only, SELECT ANY TABLE) |
| **JDBC URL** | `jdbc:oracle:thin:@apps.example.com:1521/ebs_EBSDB` |
| **SSH** | `ssh -i ~/.ssh/google_compute_engine root@34.140.79.124` |
| **GCP Project** | components-factory-dev |
| **GCP VM** | oracle-ebs-appliance (europe-west1-b) |

### Starting the Environment (after VM restart)

```bash
ssh -i ~/.ssh/google_compute_engine root@34.140.79.124
su - oracle -c '/u01/install/APPS/scripts/startdb.sh'
su - oracle -c '/u01/install/APPS/scripts/startapps.sh'
# Wait 5 minutes for WebLogic to fully start
```

### Stopping (to save costs)

```bash
gcloud compute instances stop oracle-ebs-appliance --zone=europe-west1-b --project=components-factory-dev
```

---

## Part 1: Reading Data (Extractor)

### Method: JDBC (SQL Queries)

EBS data is in Oracle Database tables. Connect via JDBC and run SELECT queries.

**Connection string:**
```
jdbc:oracle:thin:@apps.example.com:1521/ebs_EBSDB
user: keboola_ro
password: keboola123
```

> **Note:** Use the `keboola_ro` user for external JDBC connections. The `apps` user has an EBS-internal password hash that is incompatible with some thin/lightweight JDBC drivers. `keboola_ro` has `SELECT ANY TABLE` privilege and a standard password hash compatible with all drivers including Python `oracledb` thin mode.
>
> Tables are in the `APPS` schema, so prefix with `apps.`:
> ```sql
> SELECT * FROM apps.ap_invoices_all WHERE ROWNUM <= 10
> ```

### What Data Is Available

Vision Demo contains millions of records across all EBS modules:

| Module | Key Table | Rows | Description |
|--------|-----------|------|-------------|
| **Accounts Payable** | ap_invoices_all | 145,489 | Supplier invoices |
| | ap_suppliers | 426 | Vendor master data |
| **General Ledger** | gl_je_headers | 177,917 | Journal headers |
| | gl_je_lines | 3,155,216 | Journal lines |
| | gl_balances | 8,232,309 | Account balances |
| **Accounts Receivable** | ra_customer_trx_all | 69,665 | Customer invoices |
| **Purchasing** | po_headers_all | 27,285 | Purchase orders |
| | po_lines_all | 118,894 | PO lines |
| **Inventory** | mtl_system_items_b | 27,712 | Items master |
| **HR** | per_all_people_f | 33,854 | Employees |
| **Customers (TCA)** | hz_parties | 40,836 | Parties (customers, orgs, persons) |
| | hz_cust_accounts | 1,048 | Customer accounts |
| **Foundation** | fnd_user | 3,369 | EBS users |

### Tested Queries

#### AP Invoices with Supplier Name
```sql
SELECT ai.invoice_id, ai.invoice_num, s.vendor_name, 
       ai.invoice_amount, ai.invoice_currency_code, ai.invoice_date
FROM ap_invoices_all ai, ap_suppliers s
WHERE ai.vendor_id = s.vendor_id 
  AND ai.org_id = 204
  AND ROWNUM <= 100
```
*Tested: returns data (e.g. invoice ERS-8006-109098, 12130.49 EUR)*

#### GL Journal Entries
```sql
SELECT jeh.je_header_id, jeh.name, jeh.period_name, jeh.currency_code,
       jel.je_line_num, jel.entered_dr, jel.entered_cr,
       gcc.segment1, gcc.segment2, gcc.segment3
FROM gl_je_headers jeh
JOIN gl_je_lines jel ON jeh.je_header_id = jel.je_header_id
JOIN gl_code_combinations gcc ON jel.code_combination_id = gcc.code_combination_id
WHERE jeh.ledger_id = 1 AND ROWNUM <= 100
```
*Tested: returns data (3.1M lines available)*

#### GL Balances
```sql
SELECT gl.name AS ledger, gb.currency_code, gb.period_name,
       gb.begin_balance_dr, gb.begin_balance_cr,
       gb.period_net_dr, gb.period_net_cr
FROM gl_balances gb
JOIN gl_ledgers gl ON gb.ledger_id = gl.ledger_id
WHERE gb.ledger_id = 82 AND ROWNUM <= 100
```
*Tested: returns data (Vision ADB Holdings UK, GBP, balances in millions)*

#### Purchase Orders with Lines
```sql
SELECT ph.segment1 AS po_number, ph.type_lookup_code, 
       pl.line_num, pl.item_description, pl.unit_price, pl.quantity
FROM po_headers_all ph
JOIN po_lines_all pl ON ph.po_header_id = pl.po_header_id
WHERE ph.org_id = 204 AND ROWNUM <= 100
```
*Tested: returns data (e.g. PO 2521 STANDARD with lines)*

#### Customers
```sql
SELECT hp.party_id, hp.party_name, hp.party_type, 
       hca.account_number, hca.account_name
FROM hz_parties hp
LEFT JOIN hz_cust_accounts hca ON hp.party_id = hca.party_id
WHERE hp.party_type = 'ORGANIZATION' AND ROWNUM <= 100
```
*Tested: returns data (World of Business, AT&T, UPS...)*

#### AR Transactions (Customer Invoices)
```sql
SELECT ct.customer_trx_id, ct.trx_number, ct.trx_date, 
       ct.invoice_currency_code, hp.party_name AS customer_name
FROM ra_customer_trx_all ct
JOIN hz_cust_accounts hca ON ct.bill_to_customer_id = hca.cust_account_id
JOIN hz_parties hp ON hca.party_id = hp.party_id
WHERE ROWNUM <= 100
```

#### Employees
```sql
SELECT person_id, full_name, employee_number, 
       effective_start_date, effective_end_date
FROM per_all_people_f
WHERE current_employee_flag = 'Y' AND ROWNUM <= 100
```
*Tested: returns data (Edward Erickson #51, Jean-Louis Damais #7...)*

#### Operating Units (for filtering)
```sql
SELECT organization_id, name FROM hr_operating_units
```
*Key values: 204=Vision Operations, 1646=Vision Australia, 1668=Progress UK*

### Incremental Extraction

Most tables have `last_update_date` for incremental loads:
```sql
SELECT * FROM ap_invoices_all 
WHERE last_update_date > TO_TIMESTAMP('2026-04-01', 'YYYY-MM-DD')
```

### Multi-Org

Tables ending in `_ALL` contain data for all organizations. Filter by `org_id`:
```sql
SELECT * FROM ap_invoices_all WHERE org_id = 204  -- Vision Operations only
```

---

## Part 2: Writing Data (Writer)

Two approaches, depending on data type:

| Data Type | Method | Why |
|-----------|--------|-----|
| Customers, Parties, Addresses | **REST API** | Direct API, immediate result |
| Invoices, Journals, POs | **JDBC + Open Interface tables** | Bulk loading, standard EBS pattern |

### Method A: REST API (for master data)

#### Setup

REST services are deployed and granted. Test connectivity:
```bash
curl -s -u SYSADMIN:manager1 \
  http://apps.example.com:8000/webservices/rest/provider/isActive/ \
  | python3 -m json.tool
```
Expected: `"Output": "ACTIVE"`

#### Service Discovery (WADL)

Each service has a WADL describing available operations and parameters:
```bash
curl -s -u SYSADMIN:manager1 \
  "http://apps.example.com:8000/webservices/rest/hzparty?WADL"
```

Available services:

| Service | Alias | WADL URL |
|---------|-------|----------|
| FND_USER_PKG | fnduser | `/webservices/rest/fnduser?WADL` |
| HZ_PARTY_V2PUB | hzparty | `/webservices/rest/hzparty?WADL` |
| HZ_PARTY_SITE_V2PUB | hzpartysite | `/webservices/rest/hzpartysite?WADL` |
| HZ_CUST_ACCOUNT_V2PUB | hzcustaccount | `/webservices/rest/hzcustaccount?WADL` |
| AR_INVOICE_API_PUB | arinvoice | `/webservices/rest/arinvoice?WADL` |
| GL_JOURNAL_IMPORT_PKG | gljournal | `/webservices/rest/gljournal?WADL` |

#### Tested: Create a Person

```bash
curl -X POST -u SYSADMIN:manager1 \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://apps.example.com:8000/webservices/rest/hzparty/create_person/" \
  -d '{
    "InputParameters": {
      "P_INIT_MSG_LIST": "T",
      "P_PERSON_REC": {
        "PERSON_FIRST_NAME": "John",
        "PERSON_LAST_NAME": "Doe",
        "CREATED_BY_MODULE": "TCA_V2_API"
      }
    }
  }'
```

Response (tested 2026-04-12):
```json
{
  "OutputParameters": {
    "X_RETURN_STATUS": "S",
    "X_PARTY_ID": 476211,
    "X_PARTY_NUMBER": "59775",
    "X_PROFILE_ID": 219839
  }
}
```

#### Tested: Create an Organization

```bash
curl -X POST -u SYSADMIN:manager1 \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://apps.example.com:8000/webservices/rest/hzparty/create_organization/" \
  -d '{
    "InputParameters": {
      "P_INIT_MSG_LIST": "T",
      "P_ORGANIZATION_REC": {
        "ORGANIZATION_NAME": "Acme Corporation",
        "CREATED_BY_MODULE": "TCA_V2_API"
      }
    }
  }'
```

Response (tested 2026-04-12):
```json
{
  "OutputParameters": {
    "X_RETURN_STATUS": "S",
    "X_PARTY_ID": 476212,
    "X_PARTY_NUMBER": "59776"
  }
}
```

#### Tested: Create Customer Account

```bash
curl -X POST -u SYSADMIN:manager1 \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://apps.example.com:8000/webservices/rest/hzcustaccount/create_cust_account/" \
  -d '{
    "InputParameters": {
      "P_INIT_MSG_LIST": "T",
      "P_CUST_ACCOUNT_REC": {
        "ACCOUNT_NAME": "Acme Account",
        "CREATED_BY_MODULE": "TCA_V2_API"
      },
      "P_PERSON_REC": {
        "PERSON_FIRST_NAME": "Jane",
        "PERSON_LAST_NAME": "Smith",
        "CREATED_BY_MODULE": "TCA_V2_API"
      },
      "P_CREATE_PROFILE_AMT": "F"
    }
  }'
```

Response (tested 2026-04-12):
```json
{
  "OutputParameters": {
    "X_RETURN_STATUS": "S",
    "X_CUST_ACCOUNT_ID": 126875
  }
}
```

#### Tested: Check User Exists

```bash
curl -X POST -u SYSADMIN:manager1 \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://apps.example.com:8000/webservices/rest/fnduser/testusername/" \
  -d '{"InputParameters": {"X_USER_NAME": "SYSADMIN"}}'
```

Response: `{"OutputParameters": {"TESTUSERNAME": "2"}}` (2 = user exists)

#### Tested: Verify REST Data in Database

After creating records via REST, they are immediately visible via JDBC:
```sql
SELECT party_id, party_name, party_type, creation_date
FROM hz_parties 
WHERE creation_date > SYSDATE - 1
ORDER BY creation_date DESC;
```
*Tested: "Keboola Verify Corp" (ORGANIZATION) and "KeboolaTest Verification" (PERSON) visible.*

#### REST Error Handling

`X_RETURN_STATUS` values:
- `S` = Success
- `E` = Expected error (check `X_MSG_DATA`)
- `U` = Unexpected error

Always check response for `ISGServiceFault` (auth/config issue) vs `OutputParameters` (API executed).

### Method B: Open Interface Tables (for transactional data)

For invoices, journals, POs - use the standard EBS Open Interface pattern via JDBC:

1. **INSERT** rows into interface table
2. **CALL** concurrent program to process them
3. **CHECK** interface table for errors

#### AP Invoice Import

```sql
-- 1. Insert header
INSERT INTO ap_invoices_interface (
  invoice_id, invoice_num, invoice_type_lookup_code, invoice_date,
  vendor_id, vendor_site_id, invoice_amount, invoice_currency_code,
  source, group_id, org_id
) VALUES (
  ap_invoices_interface_s.NEXTVAL, 'KB-001', 'STANDARD', SYSDATE,
  :vendor_id, :vendor_site_id, 1000.00, 'USD',
  'Keboola', 'KB_BATCH_1', 204
);

-- 2. Insert lines
INSERT INTO ap_invoice_lines_interface (
  invoice_id, invoice_line_id, line_number, line_type_lookup_code,
  amount, description
) VALUES (
  :invoice_id, ap_invoice_lines_interface_s.NEXTVAL, 1, 'ITEM',
  1000.00, 'Item from Keboola'
);

-- 3. Submit concurrent program (APXIIMPT = Payables Open Interface Import)
-- 4. Check: SELECT status, reject_lookup_code FROM ap_invoices_interface WHERE group_id = 'KB_BATCH_1'
```

#### GL Journal Import

```sql
-- 1. Insert into GL Interface (debit + credit lines)
INSERT INTO gl_interface (
  status, set_of_books_id, accounting_date, currency_code,
  date_created, created_by, actual_flag,
  user_je_category_name, user_je_source_name,
  entered_dr, entered_cr,
  segment1, segment2, segment3, group_id
) VALUES (
  'NEW', 1, SYSDATE, 'USD', SYSDATE, 0, 'A',
  'Adjustment', 'Keboola',
  1000.00, NULL,
  '01', '110', '7710', :group_id
);
-- (insert matching credit line with entered_cr = 1000.00)

-- 2. Submit Journal Import (GLLEZL)
-- 3. Check: SELECT status FROM gl_interface WHERE group_id = :group_id
```

#### PO Import

```sql
-- 1. Insert into PO Headers/Lines Interface
INSERT INTO po_headers_interface (
  interface_header_id, batch_id, process_code, action,
  org_id, document_type_code, currency_code,
  agent_id, vendor_id, vendor_site_id
) VALUES (
  po_headers_interface_s.NEXTVAL, :batch_id, 'PENDING', 'ORIGINAL',
  204, 'STANDARD', 'USD',
  :buyer_id, :vendor_id, :vendor_site_id
);

-- 2. Submit PO Import (POXPOPDOI)
-- 3. Check: SELECT process_code FROM po_headers_interface WHERE batch_id = :batch_id
```

---

## Part 3: Adding Access for a Colleague

Firewall rules are restricted to a specific IP address. To add access for another person:

```bash
# 1. Find their public IP (they run this in their terminal):
curl ifconfig.me

# 2. Update firewall rules to include their IP:
gcloud compute firewall-rules update allow-ebs-web \
  --source-ranges=109.81.169.161/32,COLLEAGUE_IP/32 \
  --project=components-factory-dev

gcloud compute firewall-rules update allow-oracle-db \
  --source-ranges=109.81.169.161/32,COLLEAGUE_IP/32 \
  --project=components-factory-dev

# 3. They add to their /etc/hosts:
#    34.140.79.124 apps.example.com

# 4. They test:
#    curl http://apps.example.com:8000/OA_HTML/AppsLocalLogin.jsp
```

To see who currently has access:
```bash
gcloud compute firewall-rules describe allow-ebs-web --project=components-factory-dev --format="value(sourceRanges)"
```

---

## Part 4: What Does NOT Work (and Why)

### SOAP - Not Available

**Issue:** SOAP endpoints at `/webservices/SOAProvider/` return HTTP 500.

**Root cause:** EBS ISG architecture has a hard split - REST runs natively on the EBS `oafm_server1` WebLogic managed server, but SOAP requires a separate **Oracle SOA Suite 12.2.1.4** installation. SOA Suite is a standalone product with its own WebLogic domain, database schemas (RCU), and license (~$57,500/processor). It is not included in the EBS VM appliance.

**Why we can't just fix it:** There is no "SOAP lite" or native SOAP mode in EBS. The `/webservices/SOAProvider/` endpoint is a proxy that routes to a SOA Suite `soa-infra` composite server. Without that server installed and configured, every SOAP call fails. Installing SOA Suite would require:
- 12-16 GB additional RAM
- Separate WebLogic domain setup
- RCU schema creation in the DB
- 2 ISG patches from My Oracle Support (which we don't have access to)
- Additional Oracle license

**Workaround:** Use REST instead. Every PL/SQL API available via SOAP is also available via REST with identical parameters and behavior. The only difference is JSON vs XML format.

### Python Thin JDBC with `apps` User - Password Hash Incompatible

**Issue:** `python-oracledb` thin mode fails with `DPY-3015: password verifier type 0x939 is not supported` when connecting as the `apps` user.

**Root cause:** EBS manages the `apps` password through its own FNDCPASS utility which creates an Oracle 10G password verifier (type 0x939). Python thin driver only supports 11G/12C verifiers.

**FIXED:** We created a dedicated `keboola_ro` database user with a standard 12C password hash and `SELECT ANY TABLE` privilege. Key steps:
1. Set `SQLNET.ALLOWED_LOGON_VERSION_SERVER=12` temporarily
2. Set `SEC_CASE_SENSITIVE_LOGON=TRUE` temporarily 
3. Create user and set password (generates 12C verifier only)
4. Restore `apps` user hash via `ALTER USER apps IDENTIFIED BY VALUES '...'` with original hash
5. Set `SEC_CASE_SENSITIVE_LOGON=FALSE` back for EBS compatibility
6. Set `SQLNET.ALLOWED_LOGON_VERSION_SERVER=8` back

```python
import oracledb
conn = oracledb.connect(user='keboola_ro', password='keboola123', dsn='apps.example.com:1521/ebs_EBSDB')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM apps.ap_invoices_all')
print(cursor.fetchone()[0])  # 145489
```

The `apps` user still works for EBS internal connections and REST API auth. For external JDBC, always use `keboola_ro`.

### REST AR Invoice - HTTP 500

**Issue:** `POST /webservices/rest/arinvoice/create_invoice/` returns HTTP 500 (Internal Server Error), not an ISG auth error.

**Root cause:** The HTTP 500 is a **PL/SQL runtime error** inside `AR_INVOICE_API_PUB.create_invoice`, not an authentication or configuration problem. The API executes but fails because the Vision Demo database has:
1. **No open AR accounting periods** - the API requires an open period for the GL_DATE. Vision demo periods are historical (2009-2012).
2. **Missing required parameters** - the API requires `batch_source_id`, `cust_trx_type_id`, `bill_to_customer_id`, `term_id`, `gl_date` at minimum.

**How to fix it:**
```bash
# Step 1: Open AR periods via EBS UI
# Login as SYSADMIN > Receivables Manager > Setup > Open/Close Periods
# Open a period for the current month

# Step 2: Use correct parameters:
curl -X POST -u SYSADMIN:manager1 \
  -H "Content-Type: application/json" \
  "http://apps.example.com:8000/webservices/rest/arinvoice/create_invoice/" \
  -d '{
    "InputParameters": {
      "RESTHeader": {
        "Responsibility": "RECEIVABLES_MANAGER",
        "RespApplication": "AR",
        "SecurityGroup": "STANDARD",
        "NLSLanguage": "AMERICAN",
        "Org_Id": "204"
      },
      "P_BATCH_SOURCE_REC": {
        "BATCH_SOURCE_ID": 1001
      },
      "P_TRX_HEADER_TBL": {
        "P_TRX_HEADER_TBL_ITEM": {
          "TRX_HEADER_ID": -1,
          "BILL_TO_CUSTOMER_ID": 1006,
          "CUST_TRX_TYPE_ID": 1,
          "TRX_DATE": "2026-04-12",
          "GL_DATE": "2026-04-12",
          "TERM_ID": 4,
          "TRX_CURRENCY": "USD"
        }
      },
      "P_TRX_LINES_TBL": {
        "P_TRX_LINES_TBL_ITEM": {
          "TRX_HEADER_ID": -1,
          "TRX_LINE_ID": -1,
          "LINE_NUMBER": 1,
          "LINE_TYPE": "LINE",
          "QUANTITY_INVOICED": 1,
          "UNIT_SELLING_PRICE": 100,
          "MEMO_LINE_ID": 1
        }
      }
    }
  }'
```

**FIXED!** Two issues were found and resolved:

1. **`FV_INSTALL` package body** (Federal Financials module) had compilation errors causing `ORA-06508` during GDF validation. Fixed by creating a stub body returning `enabled_yn = 'N'`.

2. **`ORA-06531: Reference to uninitialized collection`** - Sending `null` for PL/SQL TABLE type parameters (`P_TRX_DIST_TBL`, `P_TRX_SALESCREDITS_TBL`) causes this error. **Must send empty arrays** `{"P_TRX_DIST_TBL_ITEM": []}` instead of `null`.

Use `create_invoice` endpoint (not `create_single_invoice`). Tested 3x consecutively - all returned `X_RETURN_STATUS: "S"`.

**Working example:**

**Working REST example (tested 3x, all success):**

```bash
curl -X POST -u SYSADMIN:manager1 \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  "http://apps.example.com:8000/webservices/rest/arinvoice/create_invoice/" \
  -d '{
    "CREATE_INVOICE_Input": {
      "RESTHeader": {
        "Responsibility": "RECEIVABLES_MANAGER",
        "RespApplication": "AR",
        "SecurityGroup": "STANDARD",
        "NLSLanguage": "AMERICAN",
        "Org_Id": "204"
      },
      "InputParameters": {
        "P_API_VERSION": 1.0,
        "P_INIT_MSG_LIST": "T",
        "P_COMMIT": "T",
        "P_BATCH_SOURCE_REC": {"BATCH_SOURCE_ID": 3021},
        "P_TRX_HEADER_TBL": {
          "P_TRX_HEADER_TBL_ITEM": {
            "TRX_HEADER_ID": -1,
            "BILL_TO_CUSTOMER_ID": 1000,
            "BILL_TO_SITE_USE_ID": 1003,
            "CUST_TRX_TYPE_ID": 1,
            "TRX_DATE": "2016-12-15T00:00:00",
            "GL_DATE": "2016-12-15T00:00:00",
            "TERM_ID": 4,
            "TRX_CURRENCY": "USD"
          }
        },
        "P_TRX_LINES_TBL": {
          "P_TRX_LINES_TBL_ITEM": {
            "TRX_HEADER_ID": -1,
            "TRX_LINE_ID": -1,
            "LINE_NUMBER": 1,
            "LINE_TYPE": "LINE",
            "QUANTITY_INVOICED": 1,
            "UNIT_SELLING_PRICE": 500,
            "DESCRIPTION": "Invoice from Keboola"
          }
        },
        "P_TRX_DIST_TBL": {"P_TRX_DIST_TBL_ITEM": []},
        "P_TRX_SALESCREDITS_TBL": {"P_TRX_SALESCREDITS_TBL_ITEM": []}
      }
    }
  }'
# Returns: {"OutputParameters": {"X_RETURN_STATUS": "S"}}
```

> **Critical:** Empty collection parameters MUST be sent as `{"ITEM": []}`, NOT as `null`. Sending `null` causes `ORA-06531: Reference to uninitialized collection`.

**Alternative: Open Interface** via JDBC (for bulk loads):

```sql
INSERT INTO apps.ra_interface_lines_all (
  interface_line_id, batch_source_name, line_type,
  description, currency_code, amount,
  orig_system_bill_customer_id, cust_trx_type_id,
  term_id, org_id, conversion_type, interface_line_context,
  created_by, creation_date, last_updated_by, last_update_date
) VALUES (
  apps.ra_customer_trx_lines_s.NEXTVAL, 'EMD (Manual)', 'LINE',
  'Invoice from Keboola', 'USD', 500,
  1000, 1, 4, 204, 'User', 'KEBOOLA',
  0, SYSDATE, 0, SYSDATE
);
-- Then submit AutoInvoice concurrent program to process
```

### External IP Changes on Restart

**Issue:** VM external IP changes every time the VM is restarted.

**How to fix (optional, $4/month):**
```bash
# Reserve a static IP
gcloud compute addresses create ebs-static-ip --region=europe-west1 --project=components-factory-dev

# Get the IP
gcloud compute addresses describe ebs-static-ip --region=europe-west1 --project=components-factory-dev --format="value(address)"

# Assign to VM (VM must be stopped)
gcloud compute instances stop oracle-ebs-appliance --zone=europe-west1-b --project=components-factory-dev
gcloud compute instances delete-access-config oracle-ebs-appliance --zone=europe-west1-b --project=components-factory-dev --access-config-name="external-nat"
gcloud compute instances add-access-config oracle-ebs-appliance --zone=europe-west1-b --project=components-factory-dev --address=<STATIC_IP>
gcloud compute instances start oracle-ebs-appliance --zone=europe-west1-b --project=components-factory-dev
```

---

## Quick Test Checklist

Run these to verify the environment is working:

```bash
# 1. Web UI
curl -s -o /dev/null -w "Web UI: HTTP %{http_code}\n" http://apps.example.com:8000/OA_HTML/AppsLocalLogin.jsp

# 2. REST API
curl -s -u SYSADMIN:manager1 http://apps.example.com:8000/webservices/rest/provider/isActive/ | grep -o '"Output":"[^"]*"'

# 3. REST POST
curl -s -X POST -u SYSADMIN:manager1 -H "Content-Type: application/json" \
  "http://apps.example.com:8000/webservices/rest/fnduser/testusername/" \
  -d '{"InputParameters":{"X_USER_NAME":"SYSADMIN"}}' | grep TESTUSERNAME

# 4. DB Port
nc -z -w3 apps.example.com 1521 && echo "DB Port: OPEN" || echo "DB Port: CLOSED"

# 5. JDBC (external, Python thin mode)
python3 -c "
import oracledb
conn = oracledb.connect(user='keboola_ro', password='keboola123', dsn='apps.example.com:1521/ebs_EBSDB')
c = conn.cursor(); c.execute('SELECT COUNT(*) FROM apps.ap_invoices_all')
print('JDBC:', c.fetchone()[0], 'invoices'); conn.close()
"
```

Expected output:
```
Web UI: HTTP 200
"Output":"ACTIVE"
"TESTUSERNAME" : "2"
DB Port: OPEN
JDBC: 145489 invoices
```
