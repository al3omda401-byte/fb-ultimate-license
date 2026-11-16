# FB ULTIMATE · نظام التفعيلات

كل الملفات في **جذر الريبو** (عشان Render يبني من غير Root Directory).

- `activation.json` — مصدر الحقيقة للتفعيلات.
- `app.py` + `github_store.py` + `templates/` + `static/` — لوحة التحكم (FastAPI).
- `render.yaml` — إعدادات النشر على Render.

## القاعدة
```json
{ "all_active": true, "devices": [ { "id": "UUID", "active": true } ] }
```
- `all_active: true` → كل الأجهزة مفعّلة.
- غير كده → الجهاز لازم يكون موجود بـ`active: true`.

## إعدادات Render
| الحقل | القيمة |
|---|---|
| Root Directory | **اتركه فاضي** |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/healthz` |

**Environment Variables:** `GITHUB_TOKEN` · `GITHUB_REPO` · `ACTIVATION_PATH` · `BRANCH` ·
`PYTHON_VERSION=3.12.10` · `ADMIN_USER` · `ADMIN_PASSWORD` · `SECRET_KEY`

## رابط التفعيل اللي البرنامج بيقراه
`https://raw.githubusercontent.com/al3omda401-byte/fb-ultimate-license/refs/heads/main/activation.json`
