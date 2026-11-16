#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
github_store — Owner: Mr_3OmDa (El3omDa)
=========================================================================
قراءة/كتابة ملف التفعيل على GitHub عبر REST API **بأمان**:
  * قراءة الملف + الـsha الحالي.
  * كتابة بعمل commit واحد، بمعالجة تعارض الـsha (409) بإعادة القراءة والمحاولة.
  * تحقق: sha256 للمحتوى المكتوب = المحتوى اللي إحنا بعتناه (بعد الـcommit نقرأ ونتأكد).
  * dry_run لمعاينة الـpayload بدون أي كتابة.
مفيش أي توكن جوه الكود: من متغيرات البيئة فقط.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"


class GitHubError(RuntimeError):
    pass


def token_for(env_name: str = "GITHUB_TOKEN") -> str:
    value = (os.environ.get(env_name) or "").strip()
    if not value:
        raise GitHubError(f"{env_name} مش موجود في البيئة")
    return value


def repo_slug(default_owner: str = "", default_repo: str = "") -> tuple[str, str]:
    """اسم الريبو من البيئة (GITHUB_REPO=owner/name) أو القيم الافتراضية."""
    raw = (os.environ.get("GITHUB_REPO") or "").strip()
    if raw and "/" in raw:
        owner, _, name = raw.partition("/")
        return owner.strip(), name.strip()
    return default_owner, default_repo


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "fb-ultimate-license-dashboard",
    }


def _request(method: str, url: str, token: str, payload: dict | None = None,
             timeout: int = 40) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=_headers(token), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "ignore")
            return resp.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"message": body[:200]}
        return exc.code, parsed


def get_file(repo: str, path: str, token: str = "", ref: str = "") -> dict:
    """يقرا الملف ويرجّع {text, sha, sha256, size} — ملف مش موجود = {missing: True}."""
    token = token or token_for()
    url = f"{API}/repos/{repo}/contents/{urllib.parse.quote(path)}"
    if ref:
        url += f"?ref={ref}"
    status, body = _request("GET", url, token)
    if status == 404:
        return {"missing": True, "sha": "", "text": "", "sha256": "", "size": 0}
    if status != 200:
        raise GitHubError(f"GET {path} → {status}: {body.get('message')}")
    raw = base64.b64decode(body.get("content") or "")
    return {"text": raw.decode("utf-8", "replace"), "sha": body.get("sha", ""),
            "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw), "missing": False}


def put_file(repo: str, path: str, text: str, message: str, token: str = "",
             sha: str = "", branch: str = "main", dry_run: bool = False) -> dict:
    """يكتب الملف (commit) — وبيرجّع sha الـcommit. dry_run = معاينة بدون كتابة."""
    token = token or token_for()
    data = text.encode("utf-8")
    payload: dict = {"message": message, "content": base64.b64encode(data).decode("ascii"),
                     "branch": branch}
    if sha:
        payload["sha"] = sha
    url = f"{API}/repos/{repo}/contents/{urllib.parse.quote(path)}"
    if dry_run:
        return {"dry_run": True, "url": url, "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "has_sha": bool(sha)}
    status, body = _request("PUT", url, token, payload)
    if status not in (200, 201):
        raise GitHubError(f"PUT {path} → {status}: {body.get('message')}")
    return {"status": status, "commit": (body.get("commit") or {}).get("sha", ""),
            "html_url": (body.get("commit") or {}).get("html_url", ""),
            "sha256": hashlib.sha256(data).hexdigest()}


def write_json(repo: str, path: str, data: dict, message: str, token: str = "",
               branch: str = "main", attempts: int = 4) -> dict:
    """
    كتابة JSON بأمان: يقرا الـsha الحالي → يكتب → ولو حصل تعارض (409) يعيد القراءة
    ويكتب تاني (لحد `attempts`). وبعد الكتابة يتأكد إن المحتوى المرفوع = اللي بعتناه.
    """
    token = token or token_for()
    text = json.dumps(data, ensure_ascii=False, indent=2)
    last_error = ""
    for attempt in range(1, attempts + 1):
        current = get_file(repo, path, token=token)
        sha = "" if current.get("missing") else current.get("sha", "")
        try:
            result = put_file(repo, path, text, message, token=token, sha=sha, branch=branch)
        except GitHubError as exc:
            last_error = str(exc)
            time.sleep(0.8 * attempt)
            continue
        check = get_file(repo, path, token=token)
        result["verified"] = (check.get("sha256") == result.get("sha256"))
        result["attempt"] = attempt
        if result["verified"]:
            return result
        last_error = "المحتوى بعد الكتابة مش مطابق (تحقق فشل)"
        time.sleep(0.8 * attempt)
    raise GitHubError(f"فشل الكتابة بعد {attempts} محاولات: {last_error}")
