"""Oracle EBS preset SQL queries per module/entity.

Each preset defines a production-ready SELECT with proper JOINs,
incremental column tracking, and multi-org/ledger awareness.
"""

from __future__ import annotations

from datetime import datetime

MODULE_LABELS: dict[str, str] = {
    "ap": "Accounts Payable (AP)",
    "ar": "Accounts Receivable (AR)",
    "gl": "General Ledger (GL)",
    "po": "Purchasing (PO)",
    "inv": "Inventory (INV)",
    "hr": "Human Resources (HR)",
    "om": "Order Management (OM)",
    "tca": "Trading Community (TCA)",
}

PRESETS: dict[str, dict[str, dict]] = {
    "ap": {
        "ap_invoices": {
            "name": "AP Invoices",
            "query": """
                SELECT
                    i.invoice_id, i.invoice_num, i.invoice_date, i.invoice_amount,
                    i.amount_paid, i.invoice_currency_code, i.payment_status_flag,
                    i.invoice_type_lookup_code, i.description, i.vendor_id,
                    s.vendor_name, s.segment1 AS vendor_number,
                    i.vendor_site_id, vs.vendor_site_code,
                    i.org_id, i.set_of_books_id, i.gl_date,
                    i.creation_date, i.last_update_date
                FROM apps.ap_invoices_all i
                LEFT JOIN apps.ap_suppliers s ON i.vendor_id = s.vendor_id
                LEFT JOIN apps.ap_supplier_sites_all vs
                    ON i.vendor_site_id = vs.vendor_site_id AND i.org_id = vs.org_id
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["INVOICE_ID"],
            "default_output_table": "ebs_ap_invoices",
            "multi_org": True,
            "uses_ledger": False,
        },
        "ap_invoice_lines": {
            "name": "AP Invoice Lines",
            "query": """
                SELECT
                    l.invoice_id, l.line_number, l.line_type_lookup_code,
                    l.amount, l.quantity_invoiced, l.unit_price,
                    l.description, l.dist_code_combination_id,
                    l.org_id, l.creation_date, l.last_update_date
                FROM apps.ap_invoice_lines_all l
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["INVOICE_ID", "LINE_NUMBER"],
            "default_output_table": "ebs_ap_invoice_lines",
            "multi_org": True,
            "uses_ledger": False,
        },
        "ap_payments": {
            "name": "AP Payments (Checks)",
            "query": """
                SELECT
                    ck.check_id, ck.check_number, ck.check_date,
                    ck.amount, ck.currency_code, ck.status_lookup_code,
                    ck.vendor_id, s.vendor_name,
                    ck.bank_account_id, ck.org_id,
                    ck.creation_date, ck.last_update_date
                FROM apps.ap_checks_all ck
                LEFT JOIN apps.ap_suppliers s ON ck.vendor_id = s.vendor_id
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["CHECK_ID"],
            "default_output_table": "ebs_ap_payments",
            "multi_org": True,
            "uses_ledger": False,
        },
        "ap_suppliers": {
            "name": "AP Suppliers",
            "query": """
                SELECT
                    s.vendor_id, s.vendor_name, s.segment1 AS vendor_number,
                    s.vendor_type_lookup_code, s.enabled_flag,
                    s.creation_date, s.last_update_date
                FROM apps.ap_suppliers s
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["VENDOR_ID"],
            "default_output_table": "ebs_ap_suppliers",
            "multi_org": False,
            "uses_ledger": False,
        },
    },
    "ar": {
        "ar_invoices": {
            "name": "AR Invoices (Transactions)",
            "query": """
                SELECT
                    ct.customer_trx_id, ct.trx_number, ct.trx_date,
                    ctt.name AS transaction_type_name,
                    ct.bill_to_customer_id, hp.party_name AS customer_name,
                    ct.invoice_currency_code, ct.exchange_rate,
                    ct.org_id, ct.creation_date, ct.last_update_date
                FROM apps.ra_customer_trx_all ct
                LEFT JOIN apps.ra_cust_trx_types_all ctt
                    ON ct.cust_trx_type_id = ctt.cust_trx_type_id AND ct.org_id = ctt.org_id
                LEFT JOIN apps.hz_cust_accounts ca ON ct.bill_to_customer_id = ca.cust_account_id
                LEFT JOIN apps.hz_parties hp ON ca.party_id = hp.party_id
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["CUSTOMER_TRX_ID"],
            "default_output_table": "ebs_ar_invoices",
            "multi_org": True,
            "uses_ledger": False,
        },
        "ar_receipts": {
            "name": "AR Cash Receipts",
            "query": """
                SELECT
                    cr.cash_receipt_id, cr.receipt_number, cr.receipt_date,
                    cr.amount, cr.currency_code, cr.status,
                    cr.pay_from_customer, hp.party_name AS customer_name,
                    cr.org_id, cr.creation_date, cr.last_update_date
                FROM apps.ar_cash_receipts_all cr
                LEFT JOIN apps.hz_cust_accounts ca ON cr.pay_from_customer = ca.cust_account_id
                LEFT JOIN apps.hz_parties hp ON ca.party_id = hp.party_id
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["CASH_RECEIPT_ID"],
            "default_output_table": "ebs_ar_receipts",
            "multi_org": True,
            "uses_ledger": False,
        },
    },
    "gl": {
        "gl_journal_lines": {
            "name": "GL Journal Lines",
            "query": """
                SELECT
                    jl.je_line_num, jl.je_header_id,
                    jh.name AS journal_name, jh.je_source, jh.je_category,
                    jh.period_name, jh.default_effective_date,
                    jh.status, jh.actual_flag,
                    jl.code_combination_id, jl.entered_dr, jl.entered_cr,
                    jl.accounted_dr, jl.accounted_cr,
                    jl.description, jl.ledger_id,
                    jl.creation_date, jl.last_update_date
                FROM apps.gl_je_lines jl
                JOIN apps.gl_je_headers jh ON jl.je_header_id = jh.je_header_id
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["JE_HEADER_ID", "JE_LINE_NUM"],
            "default_output_table": "ebs_gl_journal_lines",
            "multi_org": False,
            "uses_ledger": True,
        },
        "gl_balances": {
            "name": "GL Account Balances (Snapshot)",
            "query": """
                SELECT
                    gb.ledger_id, gb.code_combination_id,
                    gb.period_name, gb.period_year, gb.period_num,
                    gb.currency_code, gb.actual_flag,
                    gb.begin_balance_dr, gb.begin_balance_cr,
                    gb.period_net_dr, gb.period_net_cr
                FROM apps.gl_balances gb
                WHERE gb.actual_flag = 'A'
                  AND gb.currency_code != 'STAT'
            """,
            "incremental_column": None,
            "default_primary_key": ["LEDGER_ID", "CODE_COMBINATION_ID", "PERIOD_NAME", "CURRENCY_CODE"],
            "default_output_table": "ebs_gl_balances",
            "multi_org": False,
            "uses_ledger": True,
        },
        "gl_code_combinations": {
            "name": "GL Chart of Accounts",
            "query": """
                SELECT
                    gcc.code_combination_id, gcc.chart_of_accounts_id,
                    gcc.segment1, gcc.segment2, gcc.segment3,
                    gcc.segment4, gcc.segment5, gcc.segment6,
                    gcc.account_type, gcc.enabled_flag,
                    gcc.start_date_active, gcc.end_date_active,
                    gcc.last_update_date
                FROM apps.gl_code_combinations gcc
                WHERE gcc.enabled_flag = 'Y'
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["CODE_COMBINATION_ID"],
            "default_output_table": "ebs_gl_code_combinations",
            "multi_org": False,
            "uses_ledger": False,
        },
    },
    "po": {
        "po_headers": {
            "name": "Purchase Order Headers",
            "query": """
                SELECT
                    ph.po_header_id, ph.segment1 AS po_number,
                    ph.type_lookup_code, ph.authorization_status,
                    ph.vendor_id, s.vendor_name,
                    ph.vendor_site_id, ph.ship_to_location_id,
                    ph.currency_code, ph.rate, ph.rate_date,
                    ph.org_id, ph.creation_date, ph.last_update_date
                FROM apps.po_headers_all ph
                LEFT JOIN apps.po_vendors s ON ph.vendor_id = s.vendor_id
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["PO_HEADER_ID"],
            "default_output_table": "ebs_po_headers",
            "multi_org": True,
            "uses_ledger": False,
        },
        "po_lines": {
            "name": "Purchase Order Lines",
            "query": """
                SELECT
                    pl.po_line_id, pl.po_header_id, pl.line_num,
                    pl.item_id, pl.item_description, pl.unit_meas_lookup_code,
                    pl.quantity, pl.unit_price, pl.amount,
                    pl.org_id, pl.creation_date, pl.last_update_date
                FROM apps.po_lines_all pl
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["PO_LINE_ID"],
            "default_output_table": "ebs_po_lines",
            "multi_org": True,
            "uses_ledger": False,
        },
    },
    "inv": {
        "mtl_transactions": {
            "name": "Inventory Transactions",
            "query": """
                SELECT
                    mmt.transaction_id, mmt.transaction_type_id,
                    mtt.transaction_type_name,
                    mmt.inventory_item_id, mmt.organization_id,
                    mmt.subinventory_code, mmt.transaction_date,
                    mmt.transaction_quantity, mmt.primary_quantity,
                    mmt.transaction_uom, mmt.actual_cost,
                    mmt.creation_date, mmt.last_update_date
                FROM apps.mtl_material_transactions mmt
                LEFT JOIN apps.mtl_transaction_types mtt
                    ON mmt.transaction_type_id = mtt.transaction_type_id
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["TRANSACTION_ID"],
            "default_output_table": "ebs_inv_transactions",
            "multi_org": True,
            "uses_ledger": False,
        },
        "mtl_items": {
            "name": "Item Master",
            "query": """
                SELECT
                    msi.inventory_item_id, msi.organization_id,
                    msi.segment1 AS item_number, msi.description,
                    msi.item_type, msi.primary_uom_code,
                    msi.inventory_item_status_code,
                    msi.creation_date, msi.last_update_date
                FROM apps.mtl_system_items_b msi
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["INVENTORY_ITEM_ID", "ORGANIZATION_ID"],
            "default_output_table": "ebs_inv_items",
            "multi_org": True,
            "uses_ledger": False,
        },
    },
    "hr": {
        "per_employees": {
            "name": "HR Employees (Current)",
            "query": """
                SELECT
                    p.person_id, p.employee_number, p.full_name,
                    p.last_name, p.first_name,
                    a.assignment_id, a.organization_id,
                    a.job_id, a.position_id, a.grade_id,
                    a.location_id, a.supervisor_id,
                    a.effective_start_date, a.effective_end_date,
                    p.creation_date, p.last_update_date
                FROM apps.per_all_people_f p
                JOIN apps.per_all_assignments_f a ON p.person_id = a.person_id
                WHERE a.primary_flag = 'Y'
                  AND SYSDATE BETWEEN a.effective_start_date AND a.effective_end_date
                  AND SYSDATE BETWEEN p.effective_start_date AND p.effective_end_date
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["PERSON_ID", "ASSIGNMENT_ID"],
            "default_output_table": "ebs_hr_employees",
            "multi_org": True,
            "uses_ledger": False,
        },
    },
    "om": {
        "oe_order_headers": {
            "name": "Sales Order Headers",
            "query": """
                SELECT
                    oh.header_id, oh.order_number,
                    oh.ordered_date, oh.request_date,
                    oh.flow_status_code, oh.transactional_curr_code,
                    oh.sold_to_org_id, hp.party_name AS customer_name,
                    oh.org_id, oh.creation_date, oh.last_update_date
                FROM apps.oe_order_headers_all oh
                LEFT JOIN apps.hz_cust_accounts ca ON oh.sold_to_org_id = ca.cust_account_id
                LEFT JOIN apps.hz_parties hp ON ca.party_id = hp.party_id
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["HEADER_ID"],
            "default_output_table": "ebs_om_order_headers",
            "multi_org": True,
            "uses_ledger": False,
        },
        "oe_order_lines": {
            "name": "Sales Order Lines",
            "query": """
                SELECT
                    ol.line_id, ol.header_id, ol.line_number,
                    ol.ordered_item, ol.ordered_quantity,
                    ol.unit_selling_price, ol.unit_list_price,
                    ol.flow_status_code, ol.schedule_ship_date,
                    ol.org_id, ol.creation_date, ol.last_update_date
                FROM apps.oe_order_lines_all ol
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["LINE_ID"],
            "default_output_table": "ebs_om_order_lines",
            "multi_org": True,
            "uses_ledger": False,
        },
    },
    "tca": {
        "hz_parties": {
            "name": "TCA Parties",
            "query": """
                SELECT
                    hp.party_id, hp.party_number, hp.party_name,
                    hp.party_type, hp.status,
                    hp.address1, hp.city, hp.state,
                    hp.postal_code, hp.country,
                    hp.primary_phone_number, hp.email_address,
                    hp.creation_date, hp.last_update_date
                FROM apps.hz_parties hp
                WHERE hp.status = 'A'
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["PARTY_ID"],
            "default_output_table": "ebs_tca_parties",
            "multi_org": False,
            "uses_ledger": False,
        },
        "hz_cust_accounts": {
            "name": "TCA Customer Accounts",
            "query": """
                SELECT
                    hca.cust_account_id, hca.account_number, hca.account_name,
                    hca.status, hca.customer_class_code,
                    hp.party_name, hp.party_type,
                    hca.creation_date, hca.last_update_date
                FROM apps.hz_cust_accounts hca
                JOIN apps.hz_parties hp ON hca.party_id = hp.party_id
            """,
            "incremental_column": "LAST_UPDATE_DATE",
            "default_primary_key": ["CUST_ACCOUNT_ID"],
            "default_output_table": "ebs_tca_cust_accounts",
            "multi_org": False,
            "uses_ledger": False,
        },
    },
}


def get_module_list() -> list[dict[str, str]]:
    """Return available modules for UI dropdown."""
    return [{"value": k, "label": v} for k, v in MODULE_LABELS.items() if k in PRESETS]


def get_entity_list(module: str) -> list[dict[str, str]]:
    """Return available entities for a given module."""
    entities = PRESETS.get(module, {})
    return [{"value": k, "label": v["name"]} for k, v in entities.items()]


def get_preset(module: str, entity: str) -> dict | None:
    """Return a preset definition or None if not found."""
    return PRESETS.get(module, {}).get(entity)


def build_query(
    preset: dict,
    org_id: int | None = None,
    ledger_id: int | None = None,
    since_dt: datetime | None = None,
) -> tuple[str, dict]:
    """Build the final SQL and bind parameters from a preset.

    - Multi-org presets get `WHERE ... org_id = :org_id` appended.
    - Ledger presets get `WHERE ... ledger_id = :ledger_id` appended.
    - Incremental presets get `AND LAST_UPDATE_DATE > :since` appended.
    - The query is wrapped in a subquery to avoid alias conflicts.
    """
    base_sql = preset["query"].strip().rstrip(";")
    params: dict = {}
    filters: list[str] = []

    if preset.get("multi_org") and org_id is not None:
        filters.append("org_id = :org_id")
        params["org_id"] = org_id

    if preset.get("uses_ledger") and ledger_id is not None:
        filters.append("ledger_id = :ledger_id")
        params["ledger_id"] = ledger_id

    if since_dt is not None and preset.get("incremental_column"):
        col = preset["incremental_column"]
        filters.append(f"{col} > :since")
        params["since"] = since_dt

    # Wrap in subquery and apply filters on the outer level
    if filters:
        where_clause = " AND ".join(filters)
        sql = f"SELECT * FROM ({base_sql}) q WHERE {where_clause}"
    else:
        sql = base_sql

    return sql, params
