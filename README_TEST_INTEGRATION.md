# DoriKent Test Bot — Integratsiya (Ish Topish Boti)

Bu hujjat **DoriKent Test Bot** integratsiyasini tavsiflaydi. Mavjud ish topish
botining hech bir funksiyasi buzilmagan — faqat test biriktirish, tayinlash va
natijani qabul qilish qismlari qo'shilgan.

## Arxitektura

```
  ISH TOPISH BOTI (bu bot)                     DoriKent Test Bot
  ┌─────────────────────────┐                 ┌──────────────────┐
  │  aiogram polling         │                 │   Test API       │
  │  + aiohttp result server │                 │   + savollar     │
  │  bot.sqlite3 (o'z bazasi)│                 │   DoriKent DB    │
  └──────────┬──────────────┘                 └────────┬─────────┘
             │  1) GET  /api/v1/tests     (HTTPS)        │
             │  2) POST /api/v1/test/assign ───────────► │
             │                                            │
             │  3) POST /api/v1/test-results  ◄────────── │ (webhook)
             ▼
      application_tests jadvali
```

> **MUHIM:** Bu bot DoriKent botning SQLite fayliga **hech qachon** ulanmaydi.
> Faqat HTTP/HTTPS API orqali ishlaydi (`services/test_api.py`).

## Tushunchalar mos kelishi (mapping)

Bu botda alohida "ariza" jadvali yo'q — ariza roli **`interests`** jadvaliga
tegishli (nomzod vakansiyaga "📞 Aloqa so'rash" bosganda yaratiladi).

| Spec tushunchasi          | Bu botdagi qiymat            |
|---------------------------|------------------------------|
| `candidate_id`            | `seekers.id`                 |
| `telegram_id`             | `seekers.telegram_id`        |
| `application_id`          | `interests.id`               |
| `vacancy_id`              | `vacancies.id`               |
| `test_id`                 | `vacancies.test_id`          |
| `external_application_id` | `interests.id`               |

---

## 1. Yangi fayllar

| Fayl | Vazifasi |
|------|----------|
| `services/__init__.py` | services paketi |
| `services/test_api.py` | DoriKent Test API HTTP klienti (httpx): `get_tests`, `assign_test`, `get_assignment`, `get_result` |
| `services/result_api.py` | Natija qabul qiluvchi aiohttp server (`POST /api/v1/test-results`), Bearer auth, Pydantic validatsiya, duplicate himoyasi |
| `test_integration.py` | End-to-end integratsiya testi (soxta DoriKent API bilan) |
| `README_TEST_INTEGRATION.md` | Ushbu hujjat |

## 2. O'zgartirilgan fayllar

| Fayl | O'zgarish |
|------|-----------|
| `config.py` | Yangi `.env` o'qishlari + `dorikent_integration_enabled()` |
| `.env`, `.env.example` | Yangi kalitlar |
| `requirements.txt` | `httpx`, `aiohttp` qo'shildi |
| `database.py` | `vacancies` ga `test_id`, `test_title`, `test_required`; yangi `application_tests` jadvali va metodlar |
| `keyboards.py` | Test menyu/tanlov klaviaturalari, deep-link tugmasi, test filtri |
| `main.py` | Test tayinlash oqimi, admin biriktirish handlerlari, "Mening arizam" va admin ko'rinishida natija, filtr, Excel ustunlari, fon retry vazifa, result API ishga tushirish |

## 3. Yangi database jadvallari va ustunlari

**`vacancies`** (qo'shilgan ustunlar, mavjud ma'lumot buzilmaydi):
- `test_id INTEGER` — biriktirilgan test (NULL bo'lsa test yo'q)
- `test_title TEXT` — test nomi (ko'rsatish uchun cache)
- `test_required INTEGER DEFAULT 0` — test majburiyligi

**`application_tests`** (yangi jadval):
`id, application_id, candidate_id, telegram_id, vacancy_id, test_id, test_title,
assignment_id, status, total_questions, correct_answers, wrong_answers, score,
percentage, result_status, sync_status, sync_error, sync_attempts, next_retry_at,
assigned_at, started_at, completed_at, created_at, updated_at`

- `status`: `assigned | started | completed | passed | failed | expired`
- `sync_status`: `sync_pending | synced | failed` (offline/retry uchun)
- `assignment_id` — unikal indeks (NULL bo'lmaganlar uchun) → duplicate himoyasi

Migratsiya avtomatik: `Database.init()` → `_add_column_if_missing()` va
`CREATE TABLE IF NOT EXISTS`. Idempotent (bir necha marta ishga tushsa xavfsiz).

## 4. Yangi `.env` qiymatlari

```env
DORIKENT_TEST_API_URL=https://test.example.uz     # DoriKent API bazaviy manzili
DORIKENT_TEST_API_SECRET=very_strong_secret        # DoriKent'ga so'rov secret (Bearer)
DORIKENT_TEST_BOT_USERNAME=DoriKentTestBot          # deep-link uchun username
TEST_RESULT_API_SECRET=another_strong_secret        # natijani qabul qilish secret (Bearer)
RESULT_API_HOST=0.0.0.0                              # result server host
RESULT_API_PORT=8080                                # result server port (Railway: PORT)
DORIKENT_TEST_API_TIMEOUT=15                         # so'rov timeout (soniya)
```

> Agar `DORIKENT_TEST_API_URL` yoki `DORIKENT_TEST_API_SECRET` bo'sh bo'lsa,
> integratsiya avtomatik **o'chiq** bo'ladi va bot avvalgidek ishlayveradi
> (testlar tayinlanmaydi).

## 5. API endpointlar

### Biz chaqiramiz (DoriKent tomonida bo'lishi kerak)
- `GET  /api/v1/tests` — aktiv testlar ro'yxati
- `POST /api/v1/test/assign` — testni nomzodga tayinlash
- `GET  /api/v1/test/assignment/{id}` — tayinlov holati (ixtiyoriy)
- `GET  /api/v1/test/result/{id}` — natija (webhook alternativasi, ixtiyoriy)

Har bir so'rovda: `Authorization: Bearer <DORIKENT_TEST_API_SECRET>`

`POST /api/v1/test/assign` tanasi:
```json
{ "candidate_id": 482, "telegram_id": 123456789, "vacancy_id": 25,
  "test_id": 7, "external_application_id": 901 }
```
Kutilgan javob: `{ "assignment_id": 1001, "test_title": "...", "total_questions": 20 }`

### Biz taqdim etamiz (DoriKent chaqiradi)
- `GET  /health` — holat tekshiruvi
- `POST /api/v1/test-results` — natijani qabul qilish

`POST /api/v1/test-results`:
- Header: `Authorization: Bearer <TEST_RESULT_API_SECRET>` **yoki** `X-API-Key: <secret>`
  (DoriKent ikkalasini ham yuboradi; noto'g'ri/yo'q → **401**)
- Tana (Pydantic bilan tekshiriladi):
```json
{ "result_key": "assignment_1001",
  "assignment_id": 1001, "candidate_id": 482, "telegram_id": 123456789,
  "vacancy_id": 25, "test_id": 7, "external_application_id": 901,
  "total_questions": 20, "correct_answers": 17, "wrong_answers": 3,
  "score": 85, "percentage": 85.0, "status": "passed",
  "completed_at": "2026-09-29T18:30:00Z" }
```
> **Muhim:** `percentage` **float** bo'lishi mumkin (masalan `66.7`) — DoriKent uni
> `round(correct/total*100, 1)` bilan hisoblaydi. `external_application_id` = 2-botdagi
> `interest_id` qiymati. `result_key` idempotency kaliti (ixtiyoriy — biz `assignment_id`
> bo'yicha dedup qilamiz).
Javob kodlari:
- `200` — qabul qilindi (`{"status":"ok","duplicate":false}`)
- `401` — noto'g'ri secret
- `404` — assignment topilmadi
- `409` — ma'lumotlar mos kelmadi (candidate/vacancy/test/telegram/application)
- `422` — validatsiya xatosi

**Duplicate:** bir xil `assignment_id` qayta kelsa — mavjud natija yangilanadi,
yangi yozuv yaratilmaydi.

## 6. Foydalanuvchi oqimi

1. Admin: **🏢 Vakansiyalar → ✏️ Tahrirlash → 📝 Test biriktirish**
2. Bot DoriKent'dan aktiv testlarni oladi va inline tugmalarda ko'rsatadi
3. Admin testni tanlaydi → `vacancy.test_id` saqlanadi (majburiyligini ham belgilash mumkin)
4. Nomzod vakansiyaga ariza beradi ("📞 Aloqa so'rash")
5. Agar `test_id` bor bo'lsa — DoriKent'ga `assign` yuboriladi, nomzodga
   **"📝 Testni boshlash"** deep-link tugmasi keladi:
   `https://t.me/<DORIKENT_TEST_BOT_USERNAME>?start=test_<assignment_id>`
6. Nomzod testni **DoriKent botda** ishlaydi (savollar bu botda saqlanmaydi)
7. DoriKent natijani `POST /api/v1/test-results` ga yuboradi
8. Natija **📄 Mening arizam** va admin panelida ko'rinadi

## 7. Xatoliklarga chidamlilik (offline / retry)

- DoriKent API ishlamasa: ariza **yo'qolmaydi**, `application_tests` yozuvi
  `sync_status='sync_pending'` bo'lib qoladi.
- Fon vazifa (`test_sync_worker`) har **60 soniyada** qayta urinadi:
  **1 daqiqa → 5 daqiqa → 15 daqiqa** kechikish bilan, `MAX_SYNC_ATTEMPTS=8`
  dan keyin `failed` deb belgilanadi.
- Natija esa webhook orqali real-time keladi (polling shart emas).

## 8. Logging

Admin log tizimiga yoziladigan eventlar:
`TEST_ASSIGNED`, `TEST_ASSIGN_FAILED`, `TEST_RESULT_RECEIVED`,
`TEST_RESULT_DUPLICATE`, `TEST_RESULT_INVALID`, `TEST_API_ERROR`.
Maxfiy kalitlar **hech qachon** logga yozilmaydi.

## 9. Backup

Mavjud SQLite backup tizimi o'zgarmagan. `application_tests` va yangi ustunlar
ayni `bot.sqlite3` faylida bo'lgani uchun avtomatik ravishda backupga kiradi.

## 10. Ishga tushirish

```bash
pip install -r requirements.txt
python main.py
```

Bot polling + natija API (`0.0.0.0:8080`) bir vaqtda ishga tushadi.
Railway'da `PORT` avtomatik ishlatiladi. DoriKent webhookini quyidagiga yo'naltiring:
`https://<sizning-domen>/api/v1/test-results`

## 11. Integratsiyani test qilish

### A) Mock integratsiya testi (tarmoq/token shart emas)
```bash
python test_integration.py
```
Tekshiriladi: testlar ro'yxati, test biriktirish, tayinlash, deep-link,
natija qabul qilish, duplicate, noto'g'ri secret (401), noto'g'ri assignment
(404), noto'g'ri telegram_id (409), validatsiya (422), API offline (retry).
Kutilgan natija: **16/16 test o'tdi**.

### B) HAQIQIY end-to-end test (DoriKent'ning real API serveri bilan)
```bash
python test_e2e.py
```
Bu test DoriKent'ning **haqiqiy FastAPI serverini** alohida subprocess'da (temp DB)
ishga tushiradi va butun oqimni **haqiqiy HTTP** orqali tekshiradi. Faqat Telegram
qatlami mock qilingan. Tekshiriladi: `GET /health`, `GET /tests`, `POST /assign`
(real DB yozuv), deep-link, real HTTP natija callback, **float percentage (66.7%)**,
duplicate himoya, ownership (409), `X-API-Key` auth, "Mening arizam" da natija.
Kutilgan natija: **17/17 tekshiruv o'tdi**.

> DoriKent repo yo'li boshqa joyda bo'lsa: `DORIKENT_DIR=/path/to/DORIKENT python test_e2e.py`.
> Yordamchi server skripti: `e2e_dorikent_server.py`.

## 11.1. Troubleshooting

| Muammo | Sabab / Yechim |
|--------|----------------|
| Natija kelmayapti | DoriKent `RECRUITMENT_API_URL` to'g'rimi? Ikki secret mos keladimi? |
| 401 natija API'da | `TEST_RESULT_API_SECRET` (2-bot) == `RECRUITMENT_API_SECRET` (DoriKent) bo'lishi kerak |
| 401 DoriKent API'da | `DORIKENT_TEST_API_SECRET` (2-bot) == `TEST_API_SECRET` (DoriKent) bo'lishi kerak |
| Deep-link ishlamaydi | `DORIKENT_TEST_BOT_USERNAME` == DoriKent `BOT_USERNAME`; yoki DoriKent bergan `deep_link` ishlatiladi |
| Testlar ro'yxati bo'sh | DoriKent'da aktiv va savoli bor test bormi? Inactive testlar qaytmaydi |
| 422 natija API'da | Payload turlari (`percentage` float bo'lishi mumkin) — versiyalar mos kelmasligi mumkin |

## 12. Xavfsizlik

- Har ikki yo'nalishda Bearer token; `hmac.compare_digest` bilan solishtirish
- Pydantic validatsiya (tur, oraliq: `percentage` 0–100 va h.k.)
- Ownership tekshiruvi: candidate/vacancy/test/telegram/application mosligi
- SQL injection himoyasi: barcha so'rovlar parametrlangan
- `.env` `.gitignore` da; secretlar logga chiqmaydi
- HTTPS: DoriKent API manzili HTTPS bo'lishi kerak
