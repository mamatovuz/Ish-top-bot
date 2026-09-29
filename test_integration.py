"""DoriKent Test integratsiyasi uchun end-to-end integratsiya testi.

Bu skript haqiqiy Telegram yoki haqiqiy DoriKent serverisiz ishlaydi:
 - vaqtinchalik SQLite baza yaratadi;
 - soxta (mock) DoriKent Test API serverini ko'taradi (get_tests, assign);
 - bizning natija (result) API serverimizni ko'taradi;
 - to'liq oqimni tekshiradi: test biriktirish → tayinlash → deep link →
   natija qabul qilish → duplicate → noto'g'ri secret → noto'g'ri assignment.

Ishga tushirish:
    python test_integration.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import httpx
from aiohttp import web

# Windows konsoli (cp1254 va h.k.) uchun UTF-8 chiqishni majburlaymiz.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

# .env ga bog'liq bo'lmaslik uchun test qiymatlarini import'dan OLDIN o'rnatamiz.
_TMP = Path(tempfile.mkdtemp(prefix="dorikent_test_"))
os.environ["BOT_TOKEN"] = "test:token"
os.environ["DATABASE_PATH"] = str(_TMP / "test.sqlite3")
os.environ["BACKUP_DIR"] = str(_TMP / "backups")
os.environ["DORIKENT_TEST_API_URL"] = "http://127.0.0.1:8791"
os.environ["DORIKENT_TEST_API_SECRET"] = "dorikent_secret"
os.environ["DORIKENT_TEST_BOT_USERNAME"] = "DoriKentTestBot"
os.environ["TEST_RESULT_API_SECRET"] = "result_secret"
os.environ["RESULT_API_HOST"] = "127.0.0.1"
os.environ["RESULT_API_PORT"] = "8792"

import config  # noqa: E402
from database import db  # noqa: E402
from services.test_api import test_client  # noqa: E402
from services import result_api  # noqa: E402

MOCK_PORT = 8791
RESULT_PORT = 8792

_checks: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    _checks.append((name, condition, detail))
    mark = "✅" if condition else "❌"
    print(f"{mark} {name}" + (f" — {detail}" if detail else ""))


# ── Soxta DoriKent API ──────────────────────────────────────────────────────
_ASSIGN_COUNTER = {"n": 1000}


async def mock_get_tests(request: web.Request) -> web.Response:
    if request.headers.get("Authorization") != "Bearer dorikent_secret":
        return web.json_response({"error": "unauthorized"}, status=401)
    return web.json_response(
        {
            "tests": [
                {"id": 7, "title": "Farmatsevt testi", "questions_count": 20},
                {"id": 8, "title": "Sotuvchi testi", "questions_count": 15},
            ]
        }
    )


async def mock_assign(request: web.Request) -> web.Response:
    if request.headers.get("Authorization") != "Bearer dorikent_secret":
        return web.json_response({"error": "unauthorized"}, status=401)
    body = await request.json()
    _ASSIGN_COUNTER["n"] += 1
    return web.json_response(
        {
            "assignment_id": _ASSIGN_COUNTER["n"],
            "test_title": "Farmatsevt testi",
            "total_questions": 20,
            "echo": body,
        }
    )


async def start_mock_dorikent() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/api/v1/tests", mock_get_tests)
    app.router.add_post("/api/v1/test/assign", mock_assign)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", MOCK_PORT)
    await site.start()
    return runner


async def run() -> None:
    db.init()

    # 1) Kasb + vakansiya + employer + seeker yaratamiz
    db.add_profession("Farmatsevt")
    prof = next(p for p in db.list_professions() if p["title"] == "Farmatsevt")
    employer_tg = 111111
    seeker_tg = 222222
    db.save_employer(employer_tg, {
        "full_name": "Ish Beruvchi", "organization": "DoriKent", "phone": "+998901112233",
        "region": "Toshkent", "district": None,
    })
    vacancy_id = db.save_vacancy(employer_tg, {
        "full_name": "Ish Beruvchi", "organization": "DoriKent", "phone": "+998901112233",
        "region": "Toshkent", "district": None, "profession_id": prof["id"],
        "profession_title": "Farmatsevt", "staff_count": 2, "job_type": "Offline",
        "salary": "5 000 000", "salary_amount": 5000000, "min_experience_years": 1,
        "requirements": "1 yil tajriba",
    })
    db.set_vacancy_moderation_status(vacancy_id, "approved")
    db.update_vacancy_field(vacancy_id, "active", 1)
    seeker_id = db.save_seeker(seeker_tg, {
        "photo_id": "x", "full_name": "Ali Valiyev", "age": 25, "gender": "Erkak",
        "phone": "+998907778899", "region": "Toshkent", "profession_id": prof["id"],
        "profession_title": "Farmatsevt", "experience": "2 yil", "previous_job": "Dorixona",
        "salary": "4 000 000",
    })
    db.set_seeker_moderation_status(seeker_id, "approved")

    # 2) API orqali testlar ro'yxatini olamiz
    tests = await test_client.get_tests()
    check("get_tests 2 ta test qaytardi", len(tests) == 2, f"{[t['title'] for t in tests]}")
    check("test normalizatsiya (id/title/questions)", tests[0]["id"] == 7 and tests[0]["questions_count"] == 20)

    # 3) Vakansiyaga testni biriktiramiz
    db.set_vacancy_test(vacancy_id, 7, "Farmatsevt testi", test_required=True)
    vac = db.get_vacancy(vacancy_id)
    check("vacancy.test_id saqlandi", int(vac["test_id"]) == 7)
    check("vacancy.test_required saqlandi", int(vac["test_required"]) == 1)

    # 4) Nomzod ariza topshiradi (interest) va test tayinlanadi
    interest_id = db.create_interest(vacancy_id, seeker_id, employer_tg, seeker_tg, "seeker_requested")
    assign = await test_client.assign_test(
        candidate_id=seeker_id, telegram_id=seeker_tg, vacancy_id=vacancy_id,
        test_id=7, external_application_id=interest_id,
    )
    row_id = db.create_application_test(
        application_id=interest_id, candidate_id=seeker_id, telegram_id=seeker_tg,
        vacancy_id=vacancy_id, test_id=7, test_title="Farmatsevt testi",
    )
    db.mark_application_test_assigned(row_id, assign["assignment_id"], "Farmatsevt testi", 20)
    at = db.get_application_test(row_id)
    assignment_id = int(at["assignment_id"])
    check("assign_test assignment_id qaytardi", assignment_id >= 1000)
    check("application_test synced", at["sync_status"] == "synced")

    # 5) Deep link to'g'ri yasaladimi
    from keyboards import start_test_keyboard
    kb = start_test_keyboard(config.DORIKENT_TEST_BOT_USERNAME, assignment_id)
    url = kb.inline_keyboard[0][0].url
    check("deep link to'g'ri", url == f"https://t.me/DoriKentTestBot?start=test_{assignment_id}", url)

    # 6) Natija API serverini ko'taramiz
    runner = await result_api.start_result_api()
    await asyncio.sleep(0.3)
    base = f"http://127.0.0.1:{RESULT_PORT}/api/v1/test-results"

    good_payload = {
        "assignment_id": assignment_id, "candidate_id": seeker_id, "telegram_id": seeker_tg,
        "vacancy_id": vacancy_id, "test_id": 7, "external_application_id": interest_id,
        "total_questions": 20, "correct_answers": 17, "wrong_answers": 3,
        "score": 85, "percentage": 85, "status": "passed",
        "completed_at": "2026-09-29T18:30:00Z",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        # 6a) Noto'g'ri secret → 401
        r = await client.post(base, json=good_payload, headers={"Authorization": "Bearer WRONG"})
        check("noto'g'ri secret → 401", r.status_code == 401, str(r.status_code))

        # 6b) To'g'ri natija → 200
        r = await client.post(base, json=good_payload, headers={"Authorization": "Bearer result_secret"})
        check("to'g'ri natija → 200", r.status_code == 200, str(r.status_code))
        saved = db.get_application_test_by_assignment(assignment_id)
        check("natija saqlandi (85%)", int(saved["percentage"]) == 85 and saved["result_status"] == "passed")

        # 6c) Duplicate → 200, duplicate=True, bitta yozuv
        r = await client.post(base, json=good_payload, headers={"Authorization": "Bearer result_secret"})
        check("duplicate → 200 & duplicate=True", r.status_code == 200 and r.json().get("duplicate") is True)
        rows = db.list_application_tests_by_vacancy(vacancy_id)
        check("duplicate yangi yozuv yaratmadi", len(rows) == 1, f"{len(rows)} ta")

        # 6d) Noto'g'ri assignment → 404
        bad = dict(good_payload, assignment_id=999999)
        r = await client.post(base, json=bad, headers={"Authorization": "Bearer result_secret"})
        check("noto'g'ri assignment → 404", r.status_code == 404, str(r.status_code))

        # 6e) Noto'g'ri telegram_id → 409 mismatch
        bad = dict(good_payload, telegram_id=999)
        r = await client.post(base, json=bad, headers={"Authorization": "Bearer result_secret"})
        check("noto'g'ri telegram_id → 409", r.status_code == 409, str(r.status_code))

        # 6f) Validatsiya xatosi (percentage > 100) → 422
        bad = dict(good_payload, percentage=150)
        r = await client.post(base, json=bad, headers={"Authorization": "Bearer result_secret"})
        check("validatsiya (percentage>100) → 422", r.status_code == 422, str(r.status_code))

    await runner.cleanup()

    # 7) Offline/retry: API o'chganда sync_pending bo'lib qolishi
    #    (mock serverni to'xtatib, xato secret bilan simulyatsiya qilamiz)
    from services.test_api import DoriKentTestClient, TestApiError
    broken = DoriKentTestClient(base_url="http://127.0.0.1:1", secret="x")
    failed = False
    try:
        await broken.assign_test(candidate_id=1, telegram_id=1, vacancy_id=1, test_id=1, external_application_id=1)
    except TestApiError:
        failed = True
    check("API offline → TestApiError (ariza yo'qolmaydi)", failed)

    # Yakuniy hisob
    total = len(_checks)
    passed = sum(1 for _, ok, _ in _checks if ok)
    print("\n" + "=" * 50)
    print(f"Natija: {passed}/{total} test o'tdi")
    if passed != total:
        print("Muvaffaqiyatsiz testlar:")
        for name, ok, detail in _checks:
            if not ok:
                print(f"  - {name} ({detail})")
        sys.exit(1)
    print("🎉 Barcha integratsiya testlari o'tdi!")


async def main() -> None:
    mock_runner = await start_mock_dorikent()
    await asyncio.sleep(0.3)
    try:
        await run()
    finally:
        await mock_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
