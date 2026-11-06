"""Міські дефекти: бекенд (FastAPI + SQLite)."""
import io
import json
import math
import os
import random
import re
import secrets
import sqlite3
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from pydantic import BaseModel

from .ai import CATEGORIES, EMERGENCY_DEPT, analyze

DATA = Path(os.getenv("DATA_DIR") or Path(__file__).resolve().parent.parent / "data")
PHOTOS = DATA / "photos"
PHOTOS.mkdir(parents=True, exist_ok=True)
STATIC = Path(__file__).parent / "static"

DISPATCH_USER = os.getenv("DISPATCH_USER", "dispatcher")
DISPATCH_PASSWORD = os.getenv("DISPATCH_PASSWORD", "")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "admin@example.com")  # для Nominatim User-Agent
ANALYZE_PER_HOUR = int(os.getenv("ANALYZE_PER_HOUR", "20"))

STATUSES = {"new", "assigned", "in_progress", "resolved", "rejected"}
OPEN = ("new", "assigned", "in_progress")

app = FastAPI(title="Міські дефекти")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
security = HTTPBasic()


# ---------- база ----------
def db() -> sqlite3.Connection:
    con = sqlite3.connect(DATA / "reports.db")
    con.row_factory = sqlite3.Row
    return con


with db() as con:
    con.execute("""CREATE TABLE IF NOT EXISTS reports (
        id TEXT PRIMARY KEY, created_at REAL, status TEXT, category TEXT, title TEXT, description TEXT,
        severity INTEGER, emergency INTEGER, department TEXT, address TEXT, lat REAL, lng REAL,
        comment TEXT, contact TEXT, photo TEXT, confirmations INTEGER, ai TEXT, history TEXT)""")


def row_to_dict(r: sqlite3.Row, private: bool = False) -> dict:
    d = dict(r)
    d["emergency"] = bool(d["emergency"])
    d["ai"] = json.loads(d["ai"] or "{}")
    d["history"] = json.loads(d["history"] or "[]")
    d["photo_url"] = f"/photos/{d['photo']}" if d["photo"] else None
    if not private:
        d.pop("contact", None)
    return d


# ---------- захист від зловживань ----------
_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host).split(",")[0].strip()
    q, now = _hits[ip], time.time()
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= ANALYZE_PER_HOUR:
        raise HTTPException(429, "Забагато запитів. Спробуйте пізніше.")
    q.append(now)


def dispatcher(creds: HTTPBasicCredentials = Depends(security)):
    ok = DISPATCH_PASSWORD and secrets.compare_digest(creds.username, DISPATCH_USER) \
        and secrets.compare_digest(creds.password, DISPATCH_PASSWORD)
    if not ok:
        raise HTTPException(401, "Невірний логін або пароль", headers={"WWW-Authenticate": "Basic"})


# ---------- сторінки ----------
@app.get("/")
def citizen_page():
    return FileResponse(STATIC / "index.html")


@app.get("/dispatch", dependencies=[Depends(dispatcher)])
def dispatch_page():
    return FileResponse(STATIC / "dispatch.html")


@app.get("/photos/{name}")
def photo(name: str):
    if not re.fullmatch(r"[0-9a-f]{32}\.jpg", name) or not (PHOTOS / name).exists():
        raise HTTPException(404)
    return FileResponse(PHOTOS / name, media_type="image/jpeg")


# ---------- API для мешканця ----------
_pending: dict[str, tuple[float, dict]] = {}  # photo_id -> (час, результат AI), живе 1 год


@app.post("/api/analyze", dependencies=[Depends(rate_limit)])
async def api_analyze(photo: UploadFile = File(...), comment: str = Form(""), address: str = Form("")):
    raw = await photo.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(413, "Фото завелике (максимум 20 МБ)")
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    except Exception:
        raise HTTPException(400, "Не вдалося прочитати фото. Надішліть JPG або PNG.")
    img.thumbnail((1568, 1568))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)  # повторне збереження прибирає EXIF (зокрема GPS)
    jpeg = buf.getvalue()

    try:
        result = await run_in_threadpool(analyze, jpeg, comment[:600], address[:200])
    except Exception as e:
        raise HTTPException(502, f"AI-аналіз не вдався: {e}")

    photo_id = uuid.uuid4().hex
    (PHOTOS / f"{photo_id}.jpg").write_bytes(jpeg)
    now = time.time()
    for k in [k for k, (t, _) in _pending.items() if now - t > 3600]:
        _pending.pop(k, None)
    _pending[photo_id] = (now, result)
    return {"photo_id": photo_id, "analysis": result}


class NewReport(BaseModel):
    photo_id: str
    category: str | None = None
    address: str = ""
    lat: float | None = None
    lng: float | None = None
    comment: str = ""
    contact: str = ""


def dist_m(a_lat, a_lng, b_lat, b_lng) -> float:
    r = math.pi / 180
    h = math.sin((b_lat - a_lat) * r / 2) ** 2 + math.cos(a_lat * r) * math.cos(b_lat * r) * math.sin((b_lng - a_lng) * r / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def new_id() -> str:
    return f"ZV-{datetime.now():%y%m%d}-{random.randint(1000, 9999)}"


@app.post("/api/reports")
def create_report(body: NewReport):
    item = _pending.pop(body.photo_id, None)
    if not item:
        raise HTTPException(400, "Спершу проаналізуйте фото (або минула година, спробуйте ще раз).")
    a = item[1]
    category = body.category if body.category in CATEGORIES else a["category"]
    if a["valid"]:
        dept = CATEGORIES[category][1] + (" + " + EMERGENCY_DEPT if a["emergency"] else "")
    else:
        dept = CATEGORIES["other"][1]
    has_geo = body.lat is not None and body.lng is not None and abs(body.lat) <= 90 and abs(body.lng) <= 180

    with db() as con:
        # Дублікат: та сама категорія, ще відкрита, в радіусі 40 м
        if has_geo:
            for r in con.execute(f"SELECT * FROM reports WHERE category=? AND status IN {OPEN} AND lat IS NOT NULL", (category,)):
                if dist_m(body.lat, body.lng, r["lat"], r["lng"]) <= 40:
                    hist = json.loads(r["history"]) + [{"status": r["status"], "at": time.time() * 1000,
                                                        "note": "Ще один мешканець повідомив про цю проблему"}]
                    con.execute("UPDATE reports SET confirmations=confirmations+1, history=? WHERE id=?",
                                (json.dumps(hist, ensure_ascii=False), r["id"]))
                    return {"duplicate": True, "id": r["id"], "confirmations": r["confirmations"] + 1, "department": r["department"]}

        rid = new_id()
        now_ms = time.time() * 1000
        con.execute("INSERT INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            rid, now_ms, "new", category, a["title"] if a["valid"] else "Потребує ручного розгляду", a["description"],
            a["severity"], int(a["emergency"]), dept, body.address[:200],
            body.lat if has_geo else None, body.lng if has_geo else None,
            body.comment[:600], body.contact[:120], f"{body.photo_id}.jpg", 1,
            json.dumps({k: a[k] for k in ("valid", "hazards", "action", "privacy", "confidence")}, ensure_ascii=False),
            json.dumps([{"status": "new", "at": now_ms, "note": "Заявку створено, AI визначив службу: " + dept}], ensure_ascii=False),
        ))
    return {"duplicate": False, "id": rid, "department": dept}


@app.get("/api/reports/{rid}")
def get_report(rid: str):
    with db() as con:
        r = con.execute("SELECT * FROM reports WHERE id=?", (rid.upper(),)).fetchone()
    if not r:
        raise HTTPException(404, "Заявку не знайдено")
    return row_to_dict(r)


_geo_cache: dict[tuple, str] = {}


@app.get("/api/geocode")
async def geocode(lat: float, lng: float):
    """Адреса за координатами (OpenStreetMap Nominatim, не частіше 1 запиту/с)."""
    key = (round(lat, 4), round(lng, 4))
    if key not in _geo_cache:
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get("https://nominatim.openstreetmap.org/reverse",
                                params={"lat": lat, "lon": lng, "format": "jsonv2", "accept-language": "uk", "zoom": 18},
                                headers={"User-Agent": f"city-defects/0.1 ({CONTACT_EMAIL})"})
            a = r.json().get("address", {})
            parts = [a.get("road") or a.get("pedestrian") or a.get("square"), a.get("house_number"),
                     a.get("city") or a.get("town") or a.get("village")]
            _geo_cache[key] = ", ".join(p for p in parts if p) or r.json().get("display_name", "")
        except Exception:
            return {"address": ""}
    return {"address": _geo_cache[key]}


@app.get("/api/meta")
def meta():
    return {"categories": {k: {"name": v[0], "dept": v[1]} for k, v in CATEGORIES.items()}}


# ---------- API для диспетчера ----------
@app.get("/api/admin/reports", dependencies=[Depends(dispatcher)])
def admin_reports():
    with db() as con:
        rows = con.execute("SELECT * FROM reports ORDER BY created_at DESC LIMIT 500").fetchall()
    return [row_to_dict(r, private=True) for r in rows]


class StatusChange(BaseModel):
    status: str
    note: str = ""


NOTES = {"assigned": "Призначено бригаду", "in_progress": "Бригада працює на місці",
         "resolved": "Проблему усунено", "rejected": "Відхилено диспетчером"}


@app.post("/api/admin/reports/{rid}/status", dependencies=[Depends(dispatcher)])
def change_status(rid: str, body: StatusChange):
    if body.status not in STATUSES:
        raise HTTPException(400, "Невідомий статус")
    with db() as con:
        r = con.execute("SELECT history FROM reports WHERE id=?", (rid,)).fetchone()
        if not r:
            raise HTTPException(404)
        hist = json.loads(r["history"]) + [{"status": body.status, "at": time.time() * 1000,
                                            "note": body.note[:300] or NOTES.get(body.status, "")}]
        con.execute("UPDATE reports SET status=?, history=? WHERE id=?",
                    (body.status, json.dumps(hist, ensure_ascii=False), rid))
    return {"ok": True}
