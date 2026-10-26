"""
Task 24 checks (part 2): importing customers from Excel / CSV.
"""

import io
import json
from datetime import datetime, timezone

from openpyxl import Workbook
from sqlalchemy import func, select

from app.models import Lead
from app.services import lead_import


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"}


MESSY = """Sr No.,Customer Name,Mobile No.,Lead Source,Interested In,Converted?,Amount (₹),Enquiry Date,Remarks
1,Neha Gupta,98110 44444,Insta,Zumba,Converted,"₹4,500",05/10/2026,Joined evening batch
2,Vikas Rana,9810055555,JD,Personal training,follow up,,12/10/2026,Call after 6
3,Pooja Shah,12345,Walk-in,Yoga,new,,13/10/2026,
4,Neha Gupta again,9811044444,Instagram,Zumba,new,,14/10/2026,typed twice
5,Amit Kumar,9876500001,Reference,CrossFit,No answer,,15/10/2026,
"""


def send(client, headers, content: bytes, name="customers.csv", dry_run=True, columns=None):
    data = {"columns": json.dumps(columns)} if columns else None
    return client.post("/leads/import", params={"dry_run": dry_run}, headers=headers, data=data,
                       files={"file": (name, content, "application/octet-stream")})


def count(db, business_id=1):
    return db.scalar(select(func.count(Lead.id)).where(Lead.business_id == business_id))


def test_template_download(raw_client):
    r = raw_client.get("/leads/import/template", headers=login(raw_client))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0] == "Name,Mobile,Email,Source,Service,Status,Amount,Date,Area,Notes"


def test_preview_saves_nothing(raw_client, db_session):
    before = count(db_session)
    r = send(raw_client, login(raw_client), MESSY.encode()).json()
    assert r["dry_run"] and r["rows_in_file"] == 5 and r["ready"] == 3
    assert r["columns"] == {"Customer Name": "name", "Mobile No.": "phone", "Lead Source": "source",
                            "Interested In": "service", "Converted?": "status", "Amount (₹)": "value",
                            "Enquiry Date": "date", "Remarks": "message"}
    assert r["not_used"] == ["Sr No."]
    assert r["duplicates"] == 1                                       # Neha's number twice in the file
    assert r["problems"] == [{"row": 4, "problem": "phone: doesn't look like a phone number (use 10 digits, e.g. 9811000000)"}]
    assert r["notes"] == []                                            # "No answer" is understood (= contacted)
    assert count(db_session) == before                                # nothing saved


def test_real_import(raw_client, db_session):
    before = count(db_session)
    r = send(raw_client, login(raw_client), MESSY.encode(), dry_run=False).json()
    assert not r["dry_run"] and r["ready"] == 3 and count(db_session) == before + 3
    neha = db_session.scalar(select(Lead).where(Lead.phone == "+919811044444"))
    assert (neha.name, neha.source, neha.service, neha.status, neha.job_value) == (
        "Neha Gupta", "instagram", "Zumba", "won", 4500)
    created = neha.created_at if neha.created_at.tzinfo else neha.created_at.replace(tzinfo=timezone.utc)
    assert created == datetime(2026, 10, 4, 18, 30, tzinfo=timezone.utc)      # 5 Oct, India time
    assert neha.messages[0].text == "Joined evening batch" and neha.details["imported_from"] == "customers.csv"
    vikas = db_session.scalar(select(Lead).where(Lead.phone == "+919810055555"))
    assert (vikas.source, vikas.status, vikas.job_value) == ("justdial", "contacted", None)
    amit = db_session.scalar(select(Lead).where(Lead.phone == "+919876500001"))
    assert (amit.source, amit.status) == ("referral", "contacted")           # "No answer" = we tried calling

    again = send(raw_client, login(raw_client), MESSY.encode(), dry_run=False).json()
    assert again["ready"] == 0 and again["duplicates"] == 4                    # already imported → skipped


def test_unknown_status_is_a_note_not_an_error(raw_client, db_session):
    csv = "Name,Phone,Status\nRavi,9811000111,Maybe next month\n"
    r = send(raw_client, login(raw_client), csv.encode(), dry_run=False).json()
    assert r["ready"] == 1 and r["notes"][0]["row"] == 2 and "saved as 'new'" in r["notes"][0]["problem"]
    assert db_session.scalar(select(Lead).where(Lead.phone == "+919811000111")).status == "new"


def test_existing_customers_are_skipped(raw_client, db_session):
    existing = db_session.scalar(select(Lead).where(Lead.business_id == 1, Lead.phone.is_not(None)))
    csv = f"Name,Phone\nOld Customer,{existing.phone}\nNew Customer,9811000222\n"
    r = send(raw_client, login(raw_client), csv.encode()).json()
    assert r["ready"] == 1 and r["duplicates"] == 1


def test_real_excel_file(raw_client, db_session):
    book = Workbook()
    sheet = book.active
    sheet.append(["Name", "Mobile", "Date", "Amount", "Status"])
    sheet.append(["Sanjay Arora", 9811000333, datetime(2026, 9, 1, 11, 0), 12000, "Paid"])    # numbers, real dates
    sheet.append([None, None, None, None, None])                                            # empty row
    sheet.append(["Meera Nair", "98110 00444", "02/09/2026", None, "lost"])
    out = io.BytesIO()
    book.save(out)
    r = send(raw_client, login(raw_client), out.getvalue(), name="old-register.xlsx", dry_run=False).json()
    assert r["ready"] == 2 and r["problems"] == []
    sanjay = db_session.scalar(select(Lead).where(Lead.phone == "+919811000333"))
    assert sanjay.status == "won" and sanjay.job_value == 12000


def test_windows_excel_csv_with_semicolons(raw_client):
    csv = "Name;Contact;Area\nRené D'Souza;9811000555;Café Lane\n".encode("cp1252")
    r = send(raw_client, login(raw_client), csv).json()
    assert r["ready"] == 1 and r["preview"][0]["name"] == "René D'Souza"


def test_correcting_a_column_guess(raw_client):
    csv = "Client,Mob\nTara,9811000666\n"
    first = send(raw_client, login(raw_client), csv.encode()).json()
    assert first["not_used"] == ["Mob"] and first["preview"][0]["phone"] is None
    fixed = send(raw_client, login(raw_client), csv.encode(), columns={"Mob": "phone"}).json()
    assert fixed["preview"][0]["phone"] == "+919811000666"


def test_friendly_file_errors(raw_client, monkeypatch):
    gym = login(raw_client)
    assert "couldn't find a Name or Phone" in send(raw_client, gym, b"City,Pin\nDelhi,110018\n").json()["detail"]
    old_xls = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100
    assert ".xlsx" in send(raw_client, gym, old_xls, name="old.xls").json()["detail"]
    assert send(raw_client, gym, b"").json()["detail"] == "The file is empty"
    monkeypatch.setattr(lead_import, "MAX_ROWS", 1)
    assert "Up to 1 rows" in send(raw_client, gym, MESSY.encode()).json()["detail"]


def test_imports_go_to_your_own_business(raw_client, db_session):
    before = count(db_session, 2)
    send(raw_client, login(raw_client, "garage@demo.in"), b"Name,Phone\nKaran,9811000777\n", dry_run=False)
    assert count(db_session, 2) == before + 1
    assert db_session.scalar(select(Lead).where(Lead.phone == "+919811000777")).business_id == 2
