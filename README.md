# FB ULTIMATE · نظام التفعيلات

- `activation.json` — مصدر الحقيقة للتفعيلات (كل الأجهزة أو سريالات محددة).
- `admin_dashboard/` — لوحة تحكم ويب (FastAPI) للتحكم في التفعيلات، جاهزة للنشر على Render.

## القاعدة
```json
{ "all_active": true, "devices": [ { "id": "UUID", "active": true } ] }
```
- `all_active: true` → كل الأجهزة مفعّلة.
- غير كده → الجهاز لازم يكون موجود بـ`active: true`.

## النشر على Render
1. Render → New → **Blueprint** → اختار الريبو ده (`render.yaml` موجود).
2. اضبط المتغيرات:
   - `GITHUB_TOKEN` = توكن Fine-grained PAT بصلاحية **Contents: Read and write** على الريبو ده.
   - `ADMIN_USER` / `ADMIN_PASSWORD` = بيانات دخولك للوحة.
   - `SECRET_KEY` = يتولّد تلقائيًا (أو حط نص طويل عشوائي).
3. بعد النشر: افتح رابط الخدمة → سجّل دخول → تحكم في الأجهزة.

البرنامج (FB ULTIMATE) بيقرا `activation.json` من الرابط العام:
`https://raw.githubusercontent.com/al3omda401-byte/fb-ultimate-license/refs/heads/main/activation.json`
