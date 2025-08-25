from flask import Flask, render_template, request, redirect, url_for
import mysql.connector
from flask_paginate import Pagination, get_page_parameter
import pandas as pd

app = Flask(__name__)

mydb = mysql.connector.connect(
  host="localhost",
  user="root",
  password="88888888",
  database="sesurvey"
)


def clean_field(value):
    """Remove blanks, slashes, and single quotes from a field."""
    if pd.isna(value):
        return ""
    return str(value).replace("/", "").replace("'", "").replace(" ", "").strip()


def invoice_number(value):
    """Extract numeric part of an invoice like 'SEABI-250250100002'."""
    cleaned = clean_field(value)
    return cleaned.split("-")[-1] if cleaned else ""


@app.route("/")
def index():
    # รับค่าหน้าปัจจุบันจาก query string (ค่าเริ่มต้น = 1)
    page = request.args.get(get_page_parameter(), type=int, default=1)
    per_page = request.args.get("per_page", type=int, default=10)  # ปรับได้จาก query string
    search = request.args.get("search", default="").strip()
    paid_filter = request.args.get("paid_filter", default="ALL")
    offset = (page - 1) * per_page

    cur = mydb.cursor(dictionary=True)  # dict เพื่ออ้างชื่อคอลัมน์ใน template ได้ง่าย

    conditions = []
    params = []

    if search:
        conditions.append("(i.claim LIKE %s OR i.invoice LIKE %s)")
        like = f"%{search}%"
        params.extend([like, like])

    if paid_filter == "PAID":
        conditions.append(
            """
            EXISTS (
                SELECT 1 FROM paid p
                WHERE p.claim = i.claim
                  AND REPLACE(REPLACE(i.invoiceref, '[', ''), ']', '') LIKE CONCAT('%', p.invoice, '%')
            )
            """
        )
    elif paid_filter == "UNPAID":
        conditions.append(
            """
            NOT EXISTS (
                SELECT 1 FROM paid p
                WHERE p.claim = i.claim
                  AND REPLACE(REPLACE(i.invoiceref, '[', ''), ']', '') LIKE CONCAT('%', p.invoice, '%')
            )
            """
        )

    where_clause = "WHERE " + " AND ".join(["1=1"] + conditions)

    query = f"""
        SELECT i.*,
               CASE
                   WHEN EXISTS (
                       SELECT 1
                       FROM paid p
                       WHERE p.claim = i.claim
                         AND REPLACE(REPLACE(i.invoiceref, '[', ''), ']', '') LIKE CONCAT('%', p.invoice, '%')
                   )
               THEN 'PAID'
               ELSE ''
               END AS paid_status
        FROM isurvey i
        {where_clause}
        LIMIT %s OFFSET %s
    """
    cur.execute(query, params + [per_page, offset])
    rows = cur.fetchall()

    # นับจำนวนทั้งหมดเพื่อคำนวณจำนวนหน้า
    count_query = f"SELECT COUNT(*) AS cnt FROM isurvey i {where_clause}"
    cur.execute(count_query, params)
    total = cur.fetchone()["cnt"]
    cur.close()

    # สร้าง Pagination object
    pagination = Pagination(
        page=page,
        per_page=per_page,
        total=total,
        css_framework="bootstrap5",   # ใช้สไตล์ Bootstrap 5
        record_name="records",         # ชื่อเรียก record (ไว้แสดงผลรวม)
        display_msg="กำลังแสดง {start} - {end} จากทั้งหมด {total} รายการ",
        format_total=True,
        format_number=True
    )

    return render_template(
        "index.html",
        rows=rows,
        pagination=pagination,
        page=page,
        per_page=per_page,
        total=total,
        search=search,
        paid_filter=paid_filter
    )


@app.route("/import", methods=["GET", "POST"])
def import_excel():
    data = None
    message = None
    if request.method == "POST":
        form_type = request.form.get("form_type")
        if form_type == "excel":
            file = request.files.get("file")
            if file:
                df = pd.read_excel(file, header=None)
                df = df.iloc[1:, :9]
                df.columns = [
                    "day",
                    "claim",
                    "invoice",
                    "invoiceref",
                    "no",
                    "offer",
                    "approve",
                    "status",
                    "statuskey",
                ]

                df["claim"] = df["claim"].apply(clean_field)
                df["invoice"] = df["invoice"].apply(clean_field)
                df = df[(df["claim"] != "") & (df["invoice"] != "")]

                cur = mydb.cursor()
                for _, row in df.iterrows():
                    cur.execute(
                        """
                        INSERT INTO isurvey
                        (day, claim, invoice, invoiceref, no, offer, approve, status, statuskey)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            row["day"],
                            row["claim"],
                            row["invoice"],
                            row["invoiceref"],
                            row["no"],
                            row["offer"],
                            row["approve"],
                            row["status"],
                            row["statuskey"],
                        ),
                    )
                mydb.commit()
                cur.close()
                data = df.to_dict(orient="records")
                message = "นำเข้าข้อมูลแล้ว"
        elif form_type == "manual":
            entry = {
                "day": request.form.get("day"),
                "claim": clean_field(request.form.get("claim")),
                "invoice": clean_field(request.form.get("invoice")),
                "invoiceref": request.form.get("invoiceref"),
                "no": request.form.get("no"),
                "offer": request.form.get("offer"),
                "approve": request.form.get("approve"),
                "status": request.form.get("status"),
                "statuskey": request.form.get("statuskey"),
            }
            cur = mydb.cursor()
            cur.execute(
                """
                INSERT INTO isurvey
                (day, claim, invoice, invoiceref, no, offer, approve, status, statuskey)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    entry["day"],
                    entry["claim"],
                    entry["invoice"],
                    entry["invoiceref"],
                    entry["no"],
                    entry["offer"],
                    entry["approve"],
                    entry["status"],
                    entry["statuskey"],
                ),
            )
            mydb.commit()
            cur.close()
            data = [entry]
            message = "บันทึกข้อมูลแล้ว"
    return render_template("import.html", data=data, message=message)



@app.route("/paid/import", methods=["GET", "POST"])
@app.route("/paid/add", methods=["GET", "POST"], endpoint="add_paid")
def import_paid():
    data = None
    message = None
    if request.method == "POST":
        form_type = request.form.get("form_type")
        if form_type == "excel":
            file = request.files.get("file")
            if file:
                df = pd.read_excel(file, header=None)
                df = df.iloc[1:, :4]
                df.columns = ["payment", "claim", "invoice", "amount"]
                df["claim"] = df["claim"].apply(clean_field)
                df["invoice"] = df["invoice"].apply(clean_field)
                df = df[(df["claim"] != "") & (df["invoice"] != "")]
                cur = mydb.cursor()
                for _, row in df.iterrows():
                    cur.execute(
                        "INSERT INTO paid (payment, claim, invoice, amount) VALUES (%s, %s, %s, %s)",
                        (
                            row["payment"],
                            row["claim"],
                            row["invoice"],
                            row["amount"],
                        ),
                    )
                mydb.commit()
                cur.close()
                data = df.to_dict(orient="records")
                message = "นำเข้าข้อมูลแล้ว"
        elif form_type == "manual":
            # ดึงค่าจากฟอร์มและแปลง amount ให้เป็นตัวเลขหรือ None
            amount_raw = request.form.get("amount")
            try:
                amount_val = float(amount_raw) if amount_raw else None
            except ValueError:
                amount_val = None

            entry = {
                "payment": request.form.get("payment"),
                "claim": clean_field(request.form.get("claim")),
                "invoice": clean_field(request.form.get("invoice")),
                "amount": amount_val,
            }

            cur = mydb.cursor()
            try:
                cur.execute(
                    "INSERT INTO paid (payment, claim, invoice, amount) VALUES (%s, %s, %s, %s)",
                    (
                        entry["payment"],
                        entry["claim"],
                        entry["invoice"],
                        entry["amount"],
                    ),
                )
                mydb.commit()
                if cur.rowcount == 1:
                    data = [entry]
                    message = "บันทึกข้อมูลแล้ว"
                else:
                    message = "ไม่สามารถบันทึกข้อมูลได้"
            except mysql.connector.Error as e:
                mydb.rollback()
                message = f"เกิดข้อผิดพลาดในการบันทึกข้อมูล: {e.msg if hasattr(e, 'msg') else e}"
            finally:
                cur.close()
    return render_template("paid.html", data=data, message=message)


@app.route("/paid")
def paid_redirect():
    return redirect(url_for("import_paid"))


@app.route("/manage", methods=["GET", "POST"], endpoint="manage_records")
def manage_records():
    table = request.form.get("table", request.args.get("table", "isurvey"))
    search = clean_field(request.form.get("search", request.args.get("search", "")))
    invoice_search = clean_field(
        request.form.get("invoice_search", request.args.get("invoice_search", ""))
    )
    record = None
    message = None
    fields = []

    if table not in ["isurvey", "paid"]:
        message = "เลือกฐานข้อมูลไม่ถูกต้อง"
        table = "isurvey"

    if table == "isurvey":
        fields = ["day", "claim", "invoice", "invoiceref", "no", "offer", "approve", "status", "statuskey"]
    else:
        fields = ["payment", "claim", "invoice", "amount"]

    if request.method == "POST":
        action = request.form.get("action")
        cur = mydb.cursor(dictionary=True, buffered=True)
        if action == "search":
            cur.execute(
                f"SELECT * FROM {table} WHERE REPLACE(claim, ' ', '')=%s AND SUBSTRING_INDEX(invoice, '-', -1)=%s",
                (search, invoice_search),
            )
            record = cur.fetchone()
        elif action == "update":
            values = [
                clean_field(request.form.get(f)) if f in ["claim", "invoice"] else request.form.get(f)
                for f in fields
            ]
            set_clause = ", ".join([f"{f}=%s" for f in fields])
            cur.execute(
                f"UPDATE {table} SET {set_clause} WHERE REPLACE(claim, ' ', '')=%s AND SUBSTRING_INDEX(invoice, '-', -1)=%s",
                values + [search, invoice_search],
            )
            mydb.commit()
            message = "แก้ไขข้อมูลแล้ว"
            new_claim = clean_field(request.form.get("claim"))
            new_invoice = invoice_number(request.form.get("invoice"))
            cur.execute(
                f"SELECT * FROM {table} WHERE REPLACE(claim, ' ', '')=%s AND SUBSTRING_INDEX(invoice, '-', -1)=%s",
                (new_claim, new_invoice),
            )
            record = cur.fetchone()
            search = new_claim
            invoice_search = new_invoice
        elif action == "delete":
            cur.execute(
                f"DELETE FROM {table} WHERE REPLACE(claim, ' ', '')=%s AND SUBSTRING_INDEX(invoice, '-', -1)=%s",
                (search, invoice_search),
            )
            mydb.commit()
            message = "ลบข้อมูลแล้ว"
            record = None
        cur.close()
    elif search and invoice_search:
        cur = mydb.cursor(dictionary=True, buffered=True)
        cur.execute(
            f"SELECT * FROM {table} WHERE REPLACE(claim, ' ', '')=%s AND SUBSTRING_INDEX(invoice, '-', -1)=%s",
            (search, invoice_search),
        )
        record = cur.fetchone()
        cur.close()

    return render_template(
        "manage.html",
        table=table,
        search=search,
        invoice_search=invoice_search,
        record=record,
        message=message,
        fields=fields,
    )

if __name__ == "__main__":
    app.run(debug=True)
