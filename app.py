#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
لوحة تحكم التفعيلات — Owner: Mr_3OmDa (El3omDa)
=========================================================================
لوحة أدمن كاملة (Render-ready) للتحكم في تفعيلات FB ULTIMATE المخزّنة في ملف JSON
على GitHub:

  * لوحة معلومات (KPIs): الإجمالي · النشط · قرب ينتهي · منتهي · موقوف.
  * الأجهزة: إضافة بتفعيل **7 أيام / 30 يوم / مدى الحياة / مدة مخصصة بالأيام**،
    تمديد، إيقاف/تفعيل، حذف، بحث، وفلترة (نشط/قرب ينتهي/منتهي/موقوف).
  * المفتاح العام `all_active` (كل الأجهزة مفعّلة) — من صفحة الإعدادات.
  * سجل عمليات (audit) + إعدادات (المدة الافتراضية · رابط الاشتراك · اسم النظام).
  * كل كتابة = commit واحد على GitHub بـsha آمن (409 بيتعالج) + تحقق sha256.

متغيرات البيئة:
  GITHUB_TOKEN (Contents: Read and write) · GITHUB_REPO · ADMIN_USER · ADMIN_PASSWORD
  SECRET_KEY · ACTIVATION_PATH (افتراضي activation.json) · BRANCH (افتراضي main)
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

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

PLANS = {"7d": ("7 أيام", 7), "30d": ("30 يوم", 30), "90d": ("90 يوم", 90),
         "lifetime": ("مدى الحياة", None), "custom": ("مدة مخصصة", None)}
EXPIRING_DAYS = 7

app = FastAPI(title="FB ULTIMATE · لوحة التفعيلات")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ------------------------------------------------------------------ أدوات
def now() -> datetime:
    return datetime.now()


def fmt(moment: datetime | None) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S") if moment else ""


def parse_date(text: str):
    """يقرا تاريخ من الصيغ اللي بنكتبها (تاريخ+وقت أو تاريخ بس)."""
    value = (text or "").strip()
    if not value:
        return None
    candidate = value.replace("T", " ")[:19]
    for pattern, length in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(candidate[:length], pattern)
        except Exception:
            continue
    return None


def normalize(value: str) -> str:
    return "".join(ch for ch in (value or "").upper() if ch not in " \t\r\n#-_")


def empty_store() -> Dict:
    return {"all_active": False, "updated_at": "", "updated_by": "", "devices": [],
            "log": [], "settings": {"default_plan": "30d", "default_days": 30,
                                    "subscribe_url": "https://t.me/Al3OmDa228",
                                    "system_name": "FB ULTIMATE"}}


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
    if not isinstance(store.get("settings"), dict):
        store["settings"] = empty_store()["settings"]
    store["devices"] = [d for d in (data.get("devices") or []) if isinstance(d, dict)]
    store["log"] = [l for l in (data.get("log") or []) if isinstance(l, dict)][-200:]
    store["_sha"] = info.get("sha", "")
    return store


def save_store(store: Dict, action: str, device: str = "", by: str = "admin") -> Dict:
    store = dict(store)
    store.pop("_error", None)
    store.pop("_sha", None)
    store["updated_at"] = fmt(now())
    store["updated_by"] = by
    log = [l for l in (store.get("log") or []) if isinstance(l, dict)]
    log.append({"at": store["updated_at"], "action": action, "device": device, "by": by})
    store["log"] = log[-200:]
    message = f"activation: {action}" + (f" ({str(device)[:18]})" if device else "")
    return gh.write_json(REPO, PATH, store, message)


def find_device(store: Dict, serial: str) -> Dict | None:
    target = normalize(serial)
    for device in store.get("devices") or []:
        if normalize(str(device.get("id", ""))) == target:
            return device
    return None


def compute_expiry(plan: str, days: int = 0, base: datetime | None = None) -> str:
    """يحسب تاريخ الانتهاء من الخطة: 7d/30d/90d/مدى الحياة/custom(أيام)."""
    label, fixed = PLANS.get(plan, PLANS["30d"])
    if fixed is None and plan != "custom":
        return ""                      # مدى الحياة
    amount = days if plan == "custom" else (fixed or 0)
    if amount <= 0:
        return ""
    return fmt((base or now()) + timedelta(days=int(amount)))


def device_view(device: Dict) -> Dict:
    """يحوّل الجهاز لعرض جاهز: الحالة + الأيام الباقية + نسبة الشريط."""
    out = dict(device)
    expires = parse_date(str(device.get("expires_at") or ""))
    out["plan_label"] = PLANS.get(str(device.get("plan", "")), ("مخصص", None))[0]
    if not expires:
        out.update({"state": "lifetime" if device.get("active") else "disabled",
                    "state_label": "مدى الحياة" if device.get("active") else "موقوف",
                    "remaining_days": None, "progress": 100})
        return out
    remaining = (expires - now()).days
    if not device.get("active"):
        state, label = "disabled", "موقوف"
    elif remaining < 0:
        state, label = "expired", "منتهي"
    elif remaining <= EXPIRING_DAYS:
        state, label = "expiring", f"باقي {remaining} يوم"
    else:
        state, label = "active", f"باقي {remaining} يوم"
    out.update({"state": state, "state_label": label, "remaining_days": remaining,
                "expires_display": expires.strftime("%Y-%m-%d"),
                "progress": max(0, min(100, int(remaining / 30 * 100))) if remaining >= 0 else 0})
    return out


def stats(store: Dict) -> Dict:
    devices = [device_view(d) for d in store.get("devices") or []]
    counts = {"total": len(devices), "active": 0, "expiring": 0, "expired": 0,
              "disabled": 0, "lifetime": 0}
    for item in devices:
        counts[item["state"]] = counts.get(item["state"], 0) + 1
        if item["state"] in ("active", "lifetime"):
            counts["active"] += 0 if item["state"] == "lifetime" else 1
    counts["active_all"] = counts["active"] + counts["lifetime"]
    return counts


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


def base_context(request: Request, user: str, store: Dict, **extra) -> Dict:
    context = {"user": user, "store": store, "repo": REPO, "path": PATH, "branch": BRANCH,
               "plans": PLANS, "counts": stats(store), "updated": store.get("updated_at", ""),
               "updated_by": store.get("updated_by", ""),
               "error": store.get("_error", ""), "notice": request.query_params.get("ok", ""),
               "active_page": ""}
    context.update(extra)
    return context


# ------------------------------------------------------------------ صفحات
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    if not current_user(request):
        return templates.TemplateResponse(request, "login.html", {"error": ""})
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/login")
def login(request: Request, username: str = Form(""), password: str = Form("")):
    if not ADMIN_PASSWORD or not SESSION_SECRET:
        return templates.TemplateResponse(request, "login.html", {
            "error": "المتغيرات ADMIN_PASSWORD و SECRET_KEY لازم يكونوا مضبوطين"})
    ok_user = secrets.compare_digest(username.strip(), ADMIN_USER)
    ok_pass = secrets.compare_digest(password, ADMIN_PASSWORD)
    if not (ok_user and ok_pass):
        return templates.TemplateResponse(request, "login.html",
                                          {"error": "بيانات الدخول غلط"})
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(COOKIE, make_session(username.strip()), httponly=True,
                        samesite="lax", max_age=SESSION_HOURS * 3600)
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(COOKIE)
    return response


def guard(request: Request):
    user = current_user(request)
    if not user:
        return None, RedirectResponse("/", status_code=303)
    return user, None


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user, redirect = guard(request)
    if redirect:
        return redirect
    store = load_store()
    devices = [device_view(d) for d in store.get("devices") or []]
    devices.sort(key=lambda d: (d.get("remaining_days") is None, d.get("remaining_days") or 0))
    expiring = [d for d in devices if d["state"] in ("expiring", "expired")][:8]
    recent_log = (store.get("log") or [])[-8:][::-1]
    return templates.TemplateResponse(request, "dashboard.html", base_context(
        request, user, store, devices=devices[:8], expiring=expiring, recent_log=recent_log,
        active_page="dashboard"))


@app.get("/devices", response_class=HTMLResponse)
def devices_page(request: Request, q: str = "", state: str = "all"):
    user, redirect = guard(request)
    if redirect:
        return redirect
    store = load_store()
    devices = [device_view(d) for d in store.get("devices") or []]
    query = normalize(q)
    if query:
        devices = [d for d in devices if query in normalize(str(d.get("id", "")))
                   or query in normalize(str(d.get("name", "")))
                   or query in normalize(str(d.get("note", "")))]
    if state != "all":
        devices = [d for d in devices if d["state"] == state]
    devices.sort(key=lambda d: str(d.get("added_at", "")), reverse=True)
    return templates.TemplateResponse(request, "devices.html", base_context(
        request, user, store, devices=devices, query=q, state=state,
        active_page="devices"))


@app.get("/log", response_class=HTMLResponse)
def log_page(request: Request, q: str = ""):
    user, redirect = guard(request)
    if redirect:
        return redirect
    store = load_store()
    items = [l for l in (store.get("log") or []) if isinstance(l, dict)][::-1]
    if q:
        needle = normalize(q)
        items = [l for l in items if needle in normalize(str(l.get("action", "")))
                 or needle in normalize(str(l.get("device", "")))
                 or needle in normalize(str(l.get("by", "")))]
    return templates.TemplateResponse(request, "log.html", base_context(
        request, user, store, items=items[:200], query=q, active_page="log"))


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    user, redirect = guard(request)
    if redirect:
        return redirect
    store = load_store()
    return templates.TemplateResponse(request, "settings.html", base_context(
        request, user, store, active_page="settings"))


# ------------------------------------------------------------------ أفعال
@app.post("/toggle-all")
def toggle_all(request: Request):
    user, redirect = guard(request)
    if redirect:
        return redirect
    store = load_store()
    store["all_active"] = not bool(store.get("all_active"))
    save_store(store, f"toggle_all → {store['all_active']}", by=user)
    return RedirectResponse("/settings?ok=toggle_all", status_code=303)


@app.post("/device/add")
def device_add(request: Request, serial: str = Form(""), name: str = Form(""),
               note: str = Form(""), plan: str = Form("30d"), days: int = Form(0)):
    user, redirect = guard(request)
    if redirect:
        return redirect
    serial = (serial or "").strip().upper()
    if not serial:
        return RedirectResponse("/devices", status_code=303)
    store = load_store()
    expires = compute_expiry(plan, days)
    existing = find_device(store, serial)
    if existing:
        existing.update({"name": name or existing.get("name", ""),
                         "note": note or existing.get("note", ""), "active": True,
                         "plan": plan, "days": days,
                         "activated_at": fmt(now()), "expires_at": expires,
                         "extended_by": user})
        action = f"device_update ({PLANS.get(plan, ('?', 0))[0]})"
    else:
        store.setdefault("devices", []).append({
            "id": serial, "name": name or "", "note": note or "", "active": True,
            "plan": plan, "days": days, "activated_at": fmt(now()), "expires_at": expires,
            "added_at": fmt(now()), "added_by": user})
        action = f"device_add ({PLANS.get(plan, ('?', 0))[0]})"
    save_store(store, action, serial, by=user)
    return RedirectResponse("/devices?ok=device", status_code=303)


@app.post("/device/toggle")
def device_toggle(request: Request, serial: str = Form("")):
    user, redirect = guard(request)
    if redirect:
        return redirect
    store = load_store()
    device = find_device(store, serial)
    if device:
        device["active"] = not bool(device.get("active"))
        save_store(store, f"device_toggle → {device['active']}", serial, by=user)
    return RedirectResponse("/devices?ok=device", status_code=303)


@app.post("/device/extend")
def device_extend(request: Request, serial: str = Form(""), plan: str = Form("30d"),
                  days: int = Form(0)):
    """تمديد: بيبني على التاريخ الحالي لو منتهي، أو على تاريخ الانتهاء لو لسه شغال."""
    user, redirect = guard(request)
    if redirect:
        return redirect
    store = load_store()
    device = find_device(store, serial)
    if device:
        base = parse_date(str(device.get("expires_at") or ""))
        if not base or base < now():
            base = now()
        device["expires_at"] = compute_expiry(plan, days, base=base)
        device["plan"] = plan
        device["days"] = days
        device["active"] = True
        device["last_extend"] = fmt(now())
        save_store(store, f"device_extend ({PLANS.get(plan, ('?', 0))[0]})", serial, by=user)
    return RedirectResponse("/devices?ok=device", status_code=303)


@app.post("/device/delete")
def device_delete(request: Request, serial: str = Form("")):
    user, redirect = guard(request)
    if redirect:
        return redirect
    store = load_store()
    target = normalize(serial)
    before = len(store.get("devices") or [])
    store["devices"] = [d for d in (store.get("devices") or [])
                        if normalize(str(d.get("id", ""))) != target]
    if len(store["devices"]) != before:
        save_store(store, "device_delete", serial, by=user)
    return RedirectResponse("/devices?ok=device", status_code=303)


@app.post("/settings/save")
def settings_save(request: Request, default_plan: str = Form("30d"),
                  default_days: int = Form(30), subscribe_url: str = Form(""),
                  system_name: str = Form("")):
    user, redirect = guard(request)
    if redirect:
        return redirect
    store = load_store()
    store["settings"] = {"default_plan": default_plan,
                         "default_days": max(1, int(default_days or 1)),
                         "subscribe_url": (subscribe_url or "").strip(),
                         "system_name": (system_name or "FB ULTIMATE").strip()}
    save_store(store, "settings_save", by=user)
    return RedirectResponse("/settings?ok=settings", status_code=303)


@app.get("/healthz")
def healthz():
    return {"ok": True, "repo": REPO, "path": PATH, "plans": list(PLANS)}
