from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DATABASE_PATH", ROOT / "civicpulse.db"))
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

DEPARTMENTS = {
    "ROADS": ("Roads", 48),
    "WATER": ("Water", 24),
    "SOLID_WASTE": ("Solid Waste", 24),
    "ELECTRICAL": ("Electrical", 12),
    "PUBLIC_HEALTH": ("Public Health", 36),
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            create table if not exists departments (
              code text primary key,
              name text not null,
              default_sla_hours integer not null
            );
            create table if not exists officials (
              id text primary key,
              email text unique not null,
              name text not null,
              role text not null,
              password_hash text not null
            );
            create table if not exists tickets (
              id text primary key,
              ticket_number text unique not null,
              pin_hash text not null,
              description text not null,
              category text not null,
              department_code text not null,
              priority text not null,
              status text not null,
              latitude real not null,
              longitude real not null,
              address text not null,
              before_photo text,
              after_photo text,
              closing_note text,
              assigned_to text,
              duplicate_of text,
              impact_count integer not null default 1,
              created_at text not null,
              sla_due_at text not null,
              resolved_at text
            );
            create table if not exists timeline_events (
              id text primary key,
              ticket_id text not null,
              at text not null,
              label text not null,
              detail text not null
            );
            """
        )
        for code, (name, sla) in DEPARTMENTS.items():
            conn.execute("insert or ignore into departments values (?, ?, ?)", (code, name, sla))
        users = [
            ("officer@civicpulse.local", "Asha Field Officer", "FIELD_OFFICER"),
            ("supervisor@civicpulse.local", "Ravi Supervisor", "SUPERVISOR"),
            ("commissioner@civicpulse.local", "Meera Commissioner", "COMMISSIONER"),
        ]
        for email, name, role in users:
            conn.execute(
                "insert or ignore into officials values (?, ?, ?, ?, ?)",
                (str(uuid4()), email, name, role, hash_value("password")),
            )


def classify(description: str, category: str) -> tuple[str, str]:
    text = f"{description} {category}".lower()
    if re.search(r"pothole|road|street|drain|footpath", text):
        return "ROADS", "HIGH"
    if re.search(r"water|leak|pipe|sewer|flood", text):
        return "WATER", "HIGH"
    if re.search(r"garbage|trash|waste|dump", text):
        return "SOLID_WASTE", "MEDIUM"
    if re.search(r"light|electric|wire|pole|power", text):
        return "ELECTRICAL", "URGENT"
    if re.search(r"mosquito|health|clinic|animal|sanitation", text):
        return "PUBLIC_HEALTH", "HIGH"
    return "ROADS", "MEDIUM"


def save_data_url(data_url: str | None, prefix: str) -> str | None:
    if not data_url:
        return None
    if "," not in data_url:
        return data_url
    header, payload = data_url.split(",", 1)
    ext = "jpg" if "jpeg" in header or "jpg" in header else "png"
    path = UPLOAD_DIR / f"{prefix}-{uuid4()}.{ext}"
    path.write_bytes(base64.b64decode(payload))
    return f"http://127.0.0.1:8000/uploads/{path.name}"


def add_event(conn: sqlite3.Connection, ticket_id: str, label: str, detail: str) -> None:
    conn.execute(
        "insert into timeline_events values (?, ?, ?, ?, ?)",
        (str(uuid4()), ticket_id, utcnow(), label, detail),
    )


def serialize(conn: sqlite3.Connection, row: sqlite3.Row, pin: str | None = None) -> dict:
    timeline = conn.execute(
        "select at, label, detail from timeline_events where ticket_id = ? order by at",
        (row["id"],),
    ).fetchall()
    return {
        "id": row["id"],
        "ticketNumber": row["ticket_number"],
        "pin": pin,
        "description": row["description"],
        "category": row["category"],
        "departmentCode": row["department_code"],
        "priority": row["priority"],
        "status": row["status"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "address": row["address"],
        "beforePhoto": row["before_photo"],
        "afterPhoto": row["after_photo"],
        "closingNote": row["closing_note"],
        "assignedTo": row["assigned_to"],
        "duplicateOf": row["duplicate_of"],
        "impactCount": row["impact_count"],
        "createdAt": row["created_at"],
        "slaDueAt": row["sla_due_at"],
        "resolvedAt": row["resolved_at"],
        "timeline": [dict(item) for item in timeline],
    }


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("content-length", "0"))
    return json.loads(handler.rfile.read(length) or b"{}")


class Handler(BaseHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
        super().end_headers()

    def json(self, body: object, status: int = 200) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            return self.json({"ok": True, "database": str(DB_PATH)})
        if path == "/tickets":
            with db() as conn:
                rows = conn.execute("select * from tickets order by created_at desc").fetchall()
                return self.json([serialize(conn, row) for row in rows])
        if path.startswith("/uploads/"):
            file_path = UPLOAD_DIR / Path(path).name
            if not file_path.exists():
                return self.json({"detail": "File not found"}, 404)
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg" if file_path.suffix == ".jpg" else "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.json({"detail": "Not found"}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        payload = read_json(self)
        if path == "/auth/login":
            with db() as conn:
                user = conn.execute("select * from officials where email = ?", (payload.get("email"),)).fetchone()
                if not user or user["password_hash"] != hash_value(payload.get("password", "")):
                    return self.json({"detail": "Invalid official login"}, 401)
                return self.json({"email": user["email"], "name": user["name"], "role": user["role"], "token": str(uuid4())})
        if path == "/track":
            with db() as conn:
                ticket = conn.execute("select * from tickets where ticket_number = ?", (payload.get("ticket_number", "").upper(),)).fetchone()
                if not ticket or ticket["pin_hash"] != hash_value(payload.get("pin", "")):
                    return self.json({"detail": "Ticket not found"}, 404)
                return self.json(serialize(conn, ticket))
        if path == "/tickets":
            description = payload.get("description", "").strip()
            if len(description) < 12:
                return self.json({"detail": "Description must be at least 12 characters"}, 400)
            department_code, priority = classify(description, payload.get("category", "General"))
            sla_hours = DEPARTMENTS[department_code][1]
            created = datetime.now(timezone.utc)
            pin = str(random.randint(100000, 999999))
            ticket_id = str(uuid4())
            number = f"CP-{created.year}-{random.randint(100000, 999999)}"
            with db() as conn:
                duplicate = conn.execute(
                    "select ticket_number from tickets where status != 'RESOLVED' and department_code = ? limit 1",
                    (department_code,),
                ).fetchone()
                conn.execute(
                    """
                    insert into tickets values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ticket_id,
                        number,
                        hash_value(pin),
                        description,
                        payload.get("category", "General"),
                        department_code,
                        priority,
                        "SUBMITTED",
                        payload.get("latitude"),
                        payload.get("longitude"),
                        payload.get("address", "Location provided by citizen"),
                        save_data_url(payload.get("before_photo"), "before"),
                        None,
                        None,
                        None,
                        duplicate["ticket_number"] if duplicate else None,
                        1,
                        created.isoformat(),
                        (created + timedelta(hours=sla_hours)).isoformat(),
                        None,
                    ),
                )
                add_event(conn, ticket_id, "Submitted", "Anonymous complaint received.")
                add_event(conn, ticket_id, "Triaged", f"Routed to {DEPARTMENTS[department_code][0]} with {priority.lower()} priority.")
                row = conn.execute("select * from tickets where id = ?", (ticket_id,)).fetchone()
                return self.json(serialize(conn, row, pin), 201)
        self.json({"detail": "Not found"}, 404)

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        parts = path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "tickets":
            return self.json({"detail": "Not found"}, 404)
        ticket_id, action = parts[1], parts[2]
        payload = read_json(self)
        with db() as conn:
            ticket = conn.execute("select * from tickets where id = ?", (ticket_id,)).fetchone()
            if not ticket:
                return self.json({"detail": "Ticket not found"}, 404)
            if action == "assign":
                conn.execute("update tickets set status = ?, assigned_to = ? where id = ?", ("ASSIGNED", "Municipal Officer", ticket_id))
                add_event(conn, ticket_id, "Assigned", "Assigned to municipal officer.")
            elif action == "start":
                conn.execute("update tickets set status = ? where id = ?", ("IN_PROGRESS", ticket_id))
                add_event(conn, ticket_id, "In progress", "Field work has started.")
            elif action == "resolve":
                note = payload.get("closing_note", "").strip()
                if len(note) < 20 or not payload.get("after_photo"):
                    return self.json({"detail": "After photo and 20-character closing note required"}, 400)
                conn.execute(
                    "update tickets set status = ?, after_photo = ?, closing_note = ?, resolved_at = ? where id = ?",
                    ("RESOLVED", save_data_url(payload.get("after_photo"), "after"), note, utcnow(), ticket_id),
                )
                add_event(conn, ticket_id, "Resolved", "Officer submitted after photo and closure note.")
            else:
                return self.json({"detail": "Not found"}, 404)
            row = conn.execute("select * from tickets where id = ?", (ticket_id,)).fetchone()
            return self.json(serialize(conn, row))


if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", "8000"))
    print(f"CivicPulse API running on http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
