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
    return str(value).replace("/", "").replace("'", "").strip()


@app.route("/")
def index():
    # รับค่าหน้าปัจจุบันจาก query string (ค่าเริ่มต้น = 1)
    page = request.args.get(get_page_parameter(), type=int, default=1)
    per_page = request.args.get("per_page", type=int, default=10)  # ปรับได้จาก query string
    offset = (page - 1) * per_page

    cur = mydb.cursor(dictionary=True)  # dict เพื่ออ้างชื่อคอลัมน์ใน template ได้ง่าย
    # ดึงข้อมูลจากตาราง isurvey พร้อมตรวจสอบสถานะจ่าย
    cur.execute(
        """
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
        LIMIT %s OFFSET %s
        """,
        (per_page, offset),
    )
    rows = cur.fetchall()

    # นับจำนวนทั้งหมดเพื่อคำนวณจำนวนหน้า
    cur.execute("SELECT COUNT(*) AS cnt FROM isurvey")
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
        total=total
    )


@app.route("/import", methods=["GET", "POST"])
def import_excel():
    data = None
    message = None
    if request.method == "POST":
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
    return render_template("import.html", data=data, message=message)



@app.route("/paid/import", methods=["GET", "POST"])
@app.route("/paid/add", methods=["GET", "POST"], endpoint="add_paid")
def import_paid():
    data = None
    message = None
    if request.method == "POST":
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
    return render_template("paid.html", data=data, message=message)


@app.route("/paid")
def paid_redirect():
    return redirect(url_for("import_paid"))

if __name__ == "__main__":
    app.run(debug=True)
