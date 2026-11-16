#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
لوحة تحكم التفعيلات — Owner: Mr_3OmDa (El3omDa)
=========================================================================
داشبورد ويب (Render-ready) للتحكم في تفعيلات FB ULTIMATE المخزّنة في ملف JSON
على GitHub:

  * تبديل المفتاح العام `all_active` (كل الأجهزة مفعّلة) أو تفعيل أجهزة محددة.
  * إضافة/تعديل/إيقاف/حذف جهاز (بالسريال HWID).
  * بحث + سجل عمليات (audit log جوه نفس الملف).
  * كل كتابة = commit واحد على GitHub بـsha آمن (تعارض 409 بيتعالج) + تحقق sha256.

متغيرات البيئة المطلوبة:
  GITHUB_TOKEN   : توكن Fine-grained PAT بصلاحية Contents: Read and write
  GITHUB_REPO    : owner/repo (مثال: al3omda401-byte/fb-ultimate-license)
  ADMIN_USER     : اسم مستخدم الداشبورد
  ADMIN_PASSWORD : كلمة مرور الداشبورد
  SECRET_KEY     : مفتاح توقيع الجلسة (أي نص طويل عشوائي)
اختياري:
  ACTIVATION_PATH (الافتراضي activation.json) · BRANCH (الافتراضي main)
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import github_store as gh

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_REPO = "al3omda401-byte/fb-ultimate-license"
REPO = os.environ.get("GITHUB_REPO", DEFAULT_REPO)
PATH = os.environ.get("ACTIVATION_PATH", "activation.json")
BRANCH = os.environ.get("BRANCH", "main")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SESSION_SECRET = os.environ.get("SECRET_KEY", "")
COOKIE = "fbu_session"
SESSION_HOURS = 12

app = FastAPI(title="FB ULTIMATE · لوحة التفعيلات")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ------------------------------------------------------------------ أدوات
def empty_store() -> Dict:
    return {"all_active": False, "updated_at": "", "updated_by": "",
            "devices": [], "log": []}


def normalize(value: str) -> str:
    return "".join(ch for ch in (value or "").upper() if ch not in " \t\r\n#-")


def load_store() -> Dict:
    try:
        info = gh.get_file(REPO, PATH)
    except Exception as exc:
        return {**empty_store(), "_error": f"{type(exc).__name__}: {exc}"}
    if info.get("missing") or not info.get("text"):
        return empty_store()
    try:
        data = json.loads(info["text"])
    except Exception as exc:
        return {**empty_store(), "_error": f"JSON غير صالح: {exc}"}
    store = empty_store()
    store.update({k: data.get(k, store[k]) for k in store})
    store["devices"] = [d for d in (data.get("devices") or []) if isinstance(d, dict)]
    store["log"] = [l for l in (data.get("log") or []) if isinstance(l, dict)][-80:]
    store["_sha"] = info.get("sha", "")
    return store


def save_store(store: Dict, action: str, device: str = "", by: str = "admin") -> Dict:
    store = dict(store)
    store.pop("_error", None)
    store.pop("_sha", None)
    store["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    store["updated_by"] = by
    log = [l for l in (store.get("log") or []) if isinstance(l, dict)]
    log.append({"at": store["updated_at"], "action": action, "device": device, "by": by})
    store["log"] = log[-80:]
    message = f"activation: {action}" + (f" ({device[:16]})" if device else "")
    return gh.write_json(REPO, PATH, store, message)


def find_device(store: Dict, serial: str) -> Dict | None:
    target = normalize(serial)
    for device in store.get("devices") or []:
        if normalize(str(device.get("id", ""))) == target:
            return device
    return None


# ------------------------------------------------------------------ جلسة
def make_session(user: str) -> str:
    issued = str(int(time.time()))
    payload = f"{user}|{issued}"
    signature = hmac.new(SESSION_SECRET.encode(), payload.encode(), "sha256").hexdigest()
    return f"{payload}|{signature}"


def verify_session(cookie: str) -> str:
    if not cookie or not SESSION_SECRET:
        return ""
    parts = cookie.split("|")
    if len(parts) != 3:
        return ""
    user, issued, signature = parts
    payload = f"{user}|{issued}"
    expected = hmac.new(SESSION_SECRET.encode(), payload.encode(), "sha256").hexdigest()
    if not hmac.compare_digest(signature, expected):
        return ""
    try:
        if time.time() - int(issued) > SESSION_HOURS * 3600:
            return ""
    except ValueError:
        return ""
    return user


def current_user(request: Request) -> str:
    return verify_session(request.cookies.get(COOKIE, ""))


# ------------------------------------------------------------------ صفحات
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    if not current_user(request):
        return templates.TemplateResponse("login.html",
                                          {"request": request, "error": ""})
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/login")
def login(request: Request, username: str = Form(""), password: str = Form("")):
    if not ADMIN_PASSWORD or not SESSION_SECRET:
        return templates.TemplateResponse(
            "login.html", {"request": request,
                           "error": "المتغيرات ADMIN_PASSWORD و SECRET_KEY لازم يكونوا مضبوطين"})
    ok_user = secrets.compare_digest(username.strip(), ADMIN_USER)
    ok_pass = secrets.compare_digest(password, ADMIN_PASSWORD)
    if not (ok_user and ok_pass):
        return templates.TemplateResponse("login.html",
                                          {"request": request, "error": "بيانات الدخول غلط"})
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(COOKIE, make_session(username.strip()), httponly=True,
                        samesite="lax", max_age=SESSION_HOURS * 3600)
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(COOKIE)
    return response


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, q: str = ""):
    user = current_user(request)
    if not user:
        return RedirectResponse("/", status_code=303)
    store = load_store()
    query = normalize(q)
    devices = store.get("devices") or []
    if query:
        devices = [d for d in devices if query in normalize(str(d.get("id", "")))
                   or query in normalize(str(d.get("name", "")))]
    devices = sorted(devices, key=lambda d: str(d.get("added_at", "")), reverse=True)
    active_count = sum(1 for d in store.get("devices") or [] if d.get("active"))
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user, "store": store, "devices": devices,
        "total": len(store.get("devices") or []), "active_count": active_count,
        "repo": REPO, "path": PATH, "branch": BRANCH, "query": q,
        "error": store.get("_error", ""), "notice": request.query_params.get("ok", ""),
    })


# ------------------------------------------------------------------ أفعال
def _require(request: Request):
    user = current_user(request)
    if not user:
        return None, RedirectResponse("/", status_code=303)
    return user, None


@app.post("/toggle-all")
def toggle_all(request: Request):
    user, redirect = _require(request)
    if redirect:
        return redirect
    store = load_store()
    store["all_active"] = not bool(store.get("all_active"))
    save_store(store, f"toggle_all → {store['all_active']}", by=user)
    return RedirectResponse("/dashboard?ok=toggle_all", status_code=303)


@app.post("/device/add")
def device_add(request: Request, serial: str = Form(""), name: str = Form(""),
               note: str = Form("")):
    user, redirect = _require(request)
    if redirect:
        return redirect
    serial = (serial or "").strip().upper()
    if not serial:
        return RedirectResponse("/dashboard", status_code=303)
    store = load_store()
    existing = find_device(store, serial)
    if existing:
        existing.update({"name": name or existing.get("name", ""), "active": True,
                         "note": note or existing.get("note", "")})
        action = "device_update"
    else:
        store.setdefault("devices", []).append({
            "id": serial, "name": name or "", "note": note or "", "active": True,
            "added_at": time.strftime("%Y-%m-%d %H:%M:%S"), "added_by": user})
        action = "device_add"
    save_store(store, action, serial, by=user)
    return RedirectResponse("/dashboard?ok=device", status_code=303)


@app.post("/device/toggle")
def device_toggle(request: Request, serial: str = Form("")):
    user, redirect = _require(request)
    if redirect:
        return redirect
    store = load_store()
    device = find_device(store, serial)
    if device:
        device["active"] = not bool(device.get("active"))
        save_store(store, f"device_toggle → {device['active']}", serial, by=user)
    return RedirectResponse("/dashboard?ok=device", status_code=303)


@app.post("/device/delete")
def device_delete(request: Request, serial: str = Form("")):
    user, redirect = _require(request)
    if redirect:
        return redirect
    store = load_store()
    target = normalize(serial)
    before = len(store.get("devices") or [])
    store["devices"] = [d for d in (store.get("devices") or [])
                        if normalize(str(d.get("id", ""))) != target]
    if len(store["devices"]) != before:
        save_store(store, "device_delete", serial, by=user)
    return RedirectResponse("/dashboard?ok=device", status_code=303)


@app.get("/healthz")
def healthz():
    return {"ok": True, "repo": REPO, "path": PATH}
