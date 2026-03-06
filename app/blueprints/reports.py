"""
Reports blueprint — PDF and Excel report generation
Routes (all prefixed with /api/v1 in app.py):
  GET /reports/assets/pdf      — asset register PDF
  GET /reports/assets/excel    — asset register Excel
  GET /reports/finance/pdf     — P&L summary PDF
  GET /reports/finance/excel   — cashflow Excel (2 sheets)

Query params (all optional):
  from_date, to_date, branch_id, category_id, status
"""

import io
from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required

from app import database_connection

reports_bp = Blueprint("reports", __name__)

# ---------------------------------------------------------------------------
# Lazy imports for heavy libs
# ---------------------------------------------------------------------------
def _get_reportlab():
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    return letter, landscape, SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, getSampleStyleSheet, colors, inch

def _get_openpyxl():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    return Workbook, Font, PatternFill, Alignment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fmt(val):
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return val if val is not None else ""


def _get_org_name(cursor, org_id: int) -> str:
    cursor.execute("SELECT name FROM organizations WHERE id = %s", (org_id,))
    row = cursor.fetchone()
    return row["name"] if row else "Organisation"


def _build_asset_query(org_id, branch_id=None, category_id=None, status=None,
                        from_date=None, to_date=None):
    query = """
        SELECT a.asset_tag, a.name, c.name AS category, a.location, a.branch_id,
               b.name AS branch_name, a.status, a.purchase_date,
               a.purchase_price, a.current_value, a.depreciation_rate,
               a.serial_number, a.warranty_expiry, a.assigned_to, a.notes
        FROM assets a
        LEFT JOIN asset_categories c ON c.id = a.category_id
        LEFT JOIN branches b ON b.id = a.branch_id
        WHERE a.org_id = %s
    """
    params = [org_id]
    if branch_id:
        query += " AND a.branch_id = %s"; params.append(branch_id)
    if category_id:
        query += " AND a.category_id = %s"; params.append(category_id)
    if status:
        query += " AND a.status = %s"; params.append(status)
    if from_date:
        query += " AND a.purchase_date >= %s"; params.append(from_date)
    if to_date:
        query += " AND a.purchase_date <= %s"; params.append(to_date)
    query += " ORDER BY a.name"
    return query, params


def _build_finance_query(org_id, branch_id=None, from_date=None, to_date=None):
    query = """
        SELECT t.transaction_date, t.type, fc.name AS category,
               ac.name AS account, t.amount, t.description, t.reference
        FROM transactions t
        LEFT JOIN finance_categories fc ON fc.id = t.category_id
        LEFT JOIN accounts ac ON ac.id = t.account_id
        WHERE t.org_id = %s
    """
    params = [org_id]
    if branch_id:
        query += " AND t.branch_id = %s"; params.append(branch_id)
    if from_date:
        query += " AND t.transaction_date >= %s"; params.append(from_date)
    if to_date:
        query += " AND t.transaction_date <= %s"; params.append(to_date)
    query += " ORDER BY t.transaction_date DESC"
    return query, params


# ---------------------------------------------------------------------------
# GET /reports/assets/pdf
# ---------------------------------------------------------------------------
@reports_bp.route("/reports/assets/pdf", methods=["GET"])
@jwt_required()
def assets_pdf():
    claims = get_jwt()
    org_id = claims.get("org_id")

    branch_id   = request.args.get("branch_id")
    category_id = request.args.get("category_id")
    status      = request.args.get("status")
    from_date   = request.args.get("from_date")
    to_date     = request.args.get("to_date")

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        org_name = _get_org_name(cursor, org_id)

        query, params = _build_asset_query(org_id, branch_id, category_id, status, from_date, to_date)
        cursor.execute(query, params)
        rows = cursor.fetchall()

        letter, landscape, SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, getSampleStyleSheet, colors, inch = _get_reportlab()

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(letter),
                                leftMargin=0.5*inch, rightMargin=0.5*inch,
                                topMargin=0.75*inch, bottomMargin=0.75*inch)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph(f"{org_name} — Asset Register", styles["Title"]))
        elements.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]))
        elements.append(Spacer(1, 12))

        headers = ["Tag", "Name", "Category", "Branch", "Location", "Status",
                   "Purchase Date", "Purchase Price", "Current Value"]
        data = [headers]
        for r in rows:
            data.append([
                _fmt(r.get("asset_tag")),
                _fmt(r.get("name")),
                _fmt(r.get("category")),
                _fmt(r.get("branch_name")),
                _fmt(r.get("location")),
                _fmt(r.get("status")),
                _fmt(r.get("purchase_date")),
                f"${_fmt(r.get('purchase_price') or 0):,.2f}",
                f"${_fmt(r.get('current_value') or 0):,.2f}",
            ])

        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, 0), 9),
            ("FONTSIZE",   (0, 1), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
            ("GRID",       (0, 0), (-1, -1), 0.4, colors.grey),
            ("ALIGN",      (7, 1), (-1, -1), "RIGHT"),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(table)

        doc.build(elements)
        buf.seek(0)

        return Response(
            buf.getvalue(),
            mimetype="application/pdf",
            headers={"Content-Disposition": "attachment; filename=asset_register.pdf"},
        )

    except ImportError:
        return jsonify({"success": False, "error": "reportlab not installed. Run: pip install reportlab"}), 501
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /reports/assets/excel
# ---------------------------------------------------------------------------
@reports_bp.route("/reports/assets/excel", methods=["GET"])
@jwt_required()
def assets_excel():
    claims = get_jwt()
    org_id = claims.get("org_id")

    branch_id   = request.args.get("branch_id")
    category_id = request.args.get("category_id")
    status      = request.args.get("status")
    from_date   = request.args.get("from_date")
    to_date     = request.args.get("to_date")

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        org_name = _get_org_name(cursor, org_id)

        query, params = _build_asset_query(org_id, branch_id, category_id, status, from_date, to_date)
        cursor.execute(query, params)
        rows = cursor.fetchall()

        Workbook, Font, PatternFill, Alignment = _get_openpyxl()
        wb = Workbook()
        ws = wb.active
        ws.title = "Asset Register"

        # Title row
        ws.merge_cells("A1:I1")
        ws["A1"] = f"{org_name} — Asset Register"
        ws["A1"].font = Font(bold=True, size=14)
        ws["A2"] = f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        ws["A2"].font = Font(italic=True, size=9)

        headers = ["Asset Tag", "Name", "Category", "Branch", "Location", "Status",
                   "Purchase Date", "Purchase Price", "Current Value"]
        header_fill = PatternFill(fill_type="solid", fgColor="003366")
        header_font = Font(bold=True, color="FFFFFF")

        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col_idx, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        for row_idx, r in enumerate(rows, 5):
            ws.cell(row=row_idx, column=1, value=_fmt(r.get("asset_tag")))
            ws.cell(row=row_idx, column=2, value=_fmt(r.get("name")))
            ws.cell(row=row_idx, column=3, value=_fmt(r.get("category")))
            ws.cell(row=row_idx, column=4, value=_fmt(r.get("branch_name")))
            ws.cell(row=row_idx, column=5, value=_fmt(r.get("location")))
            ws.cell(row=row_idx, column=6, value=_fmt(r.get("status")))
            ws.cell(row=row_idx, column=7, value=_fmt(r.get("purchase_date")))
            ws.cell(row=row_idx, column=8, value=float(r.get("purchase_price") or 0))
            ws.cell(row=row_idx, column=9, value=float(r.get("current_value") or 0))

        # Auto-width columns
        col_widths = [12, 25, 18, 18, 18, 12, 14, 16, 16]
        for i, width in enumerate(col_widths, 1):
            ws.column_dimensions[ws.cell(row=4, column=i).column_letter].width = width

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        return Response(
            buf.getvalue(),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=asset_register.xlsx"},
        )

    except ImportError:
        return jsonify({"success": False, "error": "openpyxl not installed. Run: pip install openpyxl"}), 501
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /reports/finance/pdf
# ---------------------------------------------------------------------------
@reports_bp.route("/reports/finance/pdf", methods=["GET"])
@jwt_required()
def finance_pdf():
    claims = get_jwt()
    org_id = claims.get("org_id")

    branch_id = request.args.get("branch_id")
    from_date = request.args.get("from_date")
    to_date   = request.args.get("to_date")

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        org_name = _get_org_name(cursor, org_id)

        query, params = _build_finance_query(org_id, branch_id, from_date, to_date)
        cursor.execute(query, params)
        rows = cursor.fetchall()

        total_income  = sum(float(r["amount"]) for r in rows if r["type"] == "income")
        total_expense = sum(float(r["amount"]) for r in rows if r["type"] == "expense")
        net = total_income - total_expense

        letter, landscape, SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, getSampleStyleSheet, colors, inch = _get_reportlab()

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(letter),
                                leftMargin=0.5*inch, rightMargin=0.5*inch,
                                topMargin=0.75*inch, bottomMargin=0.75*inch)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph(f"{org_name} — Profit & Loss Report", styles["Title"]))
        date_range = f"{from_date or 'All time'} to {to_date or 'Present'}"
        elements.append(Paragraph(f"Period: {date_range} | Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]))
        elements.append(Spacer(1, 12))

        # Summary table
        summary_data = [
            ["Metric", "Amount"],
            ["Total Income",  f"${total_income:,.2f}"],
            ["Total Expense", f"${total_expense:,.2f}"],
            ["Net Profit/Loss", f"${net:,.2f}"],
        ]
        summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME",   (0, 3), (-1, 3), "Helvetica-Bold"),
            ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#e8f5e9") if net >= 0 else colors.HexColor("#ffebee")),
            ("GRID",       (0, 0), (-1, -1), 0.4, colors.grey),
            ("ALIGN",      (1, 0), (1, -1), "RIGHT"),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 18))

        # Transactions table
        elements.append(Paragraph("Transaction Detail", styles["Heading2"]))
        elements.append(Spacer(1, 6))

        headers = ["Date", "Type", "Category", "Account", "Amount", "Description"]
        data = [headers]
        for r in rows:
            data.append([
                _fmt(r.get("transaction_date")),
                _fmt(r.get("type")),
                _fmt(r.get("category")),
                _fmt(r.get("account")),
                f"${float(r.get('amount') or 0):,.2f}",
                str(r.get("description") or "")[:60],
            ])

        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, 0), 9),
            ("FONTSIZE",   (0, 1), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
            ("GRID",       (0, 0), (-1, -1), 0.4, colors.grey),
            ("ALIGN",      (4, 1), (4, -1), "RIGHT"),
        ]))
        elements.append(table)

        doc.build(elements)
        buf.seek(0)

        return Response(
            buf.getvalue(),
            mimetype="application/pdf",
            headers={"Content-Disposition": "attachment; filename=finance_report.pdf"},
        )

    except ImportError:
        return jsonify({"success": False, "error": "reportlab not installed. Run: pip install reportlab"}), 501
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /reports/finance/excel
# ---------------------------------------------------------------------------
@reports_bp.route("/reports/finance/excel", methods=["GET"])
@jwt_required()
def finance_excel():
    claims = get_jwt()
    org_id = claims.get("org_id")

    branch_id = request.args.get("branch_id")
    from_date = request.args.get("from_date")
    to_date   = request.args.get("to_date")

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        org_name = _get_org_name(cursor, org_id)

        query, params = _build_finance_query(org_id, branch_id, from_date, to_date)
        cursor.execute(query, params)
        rows = cursor.fetchall()

        total_income  = sum(float(r["amount"]) for r in rows if r["type"] == "income")
        total_expense = sum(float(r["amount"]) for r in rows if r["type"] == "expense")
        net = total_income - total_expense

        Workbook, Font, PatternFill, Alignment = _get_openpyxl()
        wb = Workbook()

        # --- Sheet 1: Summary ---
        ws_summary = wb.active
        ws_summary.title = "Summary"
        header_fill = PatternFill(fill_type="solid", fgColor="003366")
        header_font = Font(bold=True, color="FFFFFF")

        ws_summary["A1"] = f"{org_name} — Financial Summary"
        ws_summary["A1"].font = Font(bold=True, size=14)
        date_range = f"{from_date or 'All time'} to {to_date or 'Present'}"
        ws_summary["A2"] = f"Period: {date_range}"
        ws_summary["A2"].font = Font(italic=True, size=9)

        summary_headers = ["Metric", "Amount"]
        for col_idx, h in enumerate(summary_headers, 1):
            cell = ws_summary.cell(row=4, column=col_idx, value=h)
            cell.fill = header_fill
            cell.font = header_font

        summary_rows = [
            ("Total Income", total_income),
            ("Total Expense", total_expense),
            ("Net Profit / Loss", net),
        ]
        for row_idx, (label, value) in enumerate(summary_rows, 5):
            ws_summary.cell(row=row_idx, column=1, value=label)
            cell = ws_summary.cell(row=row_idx, column=2, value=value)
            cell.number_format = '"$"#,##0.00'
            if label == "Net Profit / Loss":
                ws_summary.cell(row=row_idx, column=1).font = Font(bold=True)
                cell.font = Font(bold=True)

        ws_summary.column_dimensions["A"].width = 22
        ws_summary.column_dimensions["B"].width = 16

        # --- Sheet 2: Transactions ---
        ws_txn = wb.create_sheet("Transactions")
        ws_txn["A1"] = f"{org_name} — Transactions"
        ws_txn["A1"].font = Font(bold=True, size=14)

        txn_headers = ["Date", "Type", "Category", "Account", "Amount", "Description", "Reference"]
        for col_idx, h in enumerate(txn_headers, 1):
            cell = ws_txn.cell(row=3, column=col_idx, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        for row_idx, r in enumerate(rows, 4):
            ws_txn.cell(row=row_idx, column=1, value=_fmt(r.get("transaction_date")))
            ws_txn.cell(row=row_idx, column=2, value=_fmt(r.get("type")))
            ws_txn.cell(row=row_idx, column=3, value=_fmt(r.get("category")))
            ws_txn.cell(row=row_idx, column=4, value=_fmt(r.get("account")))
            amt_cell = ws_txn.cell(row=row_idx, column=5, value=float(r.get("amount") or 0))
            amt_cell.number_format = '"$"#,##0.00'
            ws_txn.cell(row=row_idx, column=6, value=_fmt(r.get("description")))
            ws_txn.cell(row=row_idx, column=7, value=_fmt(r.get("reference")))

        col_widths = [14, 10, 20, 20, 14, 35, 16]
        for i, width in enumerate(col_widths, 1):
            ws_txn.column_dimensions[ws_txn.cell(row=3, column=i).column_letter].width = width

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        return Response(
            buf.getvalue(),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=finance_report.xlsx"},
        )

    except ImportError:
        return jsonify({"success": False, "error": "openpyxl not installed. Run: pip install openpyxl"}), 501
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
