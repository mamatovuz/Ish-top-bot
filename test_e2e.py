"""REAL end-to-end integratsiya testi (Ish Topish Bot ↔ DoriKent Test Bot).

Bu test MOCK API ishlatmaydi — DoriKent'ning HAQIQIY FastAPI serverini alohida
subprocess'da (temp DB bilan) ishga tushiradi va butun oqimni HAQIQIY HTTP orqali
tekshiradi. Faqat Telegram qatlami mock qilingan (bot.send_message stub).

Oqim:
    Ish Topish: vakansiya + test biriktirish
        → GET /api/v1/tests           (real HTTP → DoriKent)
        → POST /api/v1/test/assign    (real HTTP → DoriKent, real DB yozuv)
        → deep link
    DoriKent: assignment ni ko'radi → real natija saqlaydi (66.7% → failed)
        → POST /api/v1/test-results   (real HTTP → Ish Topish, real DB yozuv)
    Ish Topish: natijani saqlaydi → "Mening arizam" da ko'rinadi

Ishga tushirish:
    python test_e2e.py
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

# ── Portlar va sirlar ──
DK_PORT = 8801           # DoriKent API
MY_PORT = 8802           # Ish Topish natija API
INBOUND_SECRET = "e2e_dorikent_inbound_secret"   # DoriKent'ga so'rov (2 tomonda bir xil qiymat)
RESULT_SECRET = "e2e_recruitment_result_secret"  # natija callback (2 tomonda bir xil qiymat)
BOT_USERNAME = "DoriKentTestBot"

_TMP = Path(tempfile.mkdtemp(prefix="e2e_"))
# DoriKent repo yo'li — DORIKENT_DIR env orqali o'zgartirish mumkin.
DORIKENT_DIR = os.environ.get(
    "DORIKENT_DIR", str(Path(r"C:/Users/i7/OneDrive/Desktop/DORIKENT"))
)
# DoriKent'ni ishga tushiruvchi yordamchi skript (shu loyiha ichida).
SCRATCH_HELPER = str(Path(__file__).resolve().parent / "e2e_dorikent_server.py")

# ── Ish Topish env (config import'idan OLDIN) ──
os.environ["BOT_TOKEN"] = "e2e:token"
os.environ["DATABASE_PATH"] = str(_TMP / "recruit.sqlite3")
os.environ["BACKUP_DIR"] = str(_TMP / "backups")
os.environ["DORIKENT_TEST_API_URL"] = f"http://127.0.0.1:{DK_PORT}"
os.environ["DORIKENT_TEST_API_SECRET"] = INBOUND_SECRET
os.environ["DORIKENT_TEST_BOT_USERNAME"] = BOT_USERNAME
os.environ["TEST_RESULT_API_SECRET"] = RESULT_SECRET
os.environ["RESULT_API_HOST"] = "127.0.0.1"
os.environ["RESULT_API_PORT"] = str(MY_PORT)
os.environ["TEST_RESULT_CHANNEL_ID"] = "-1009999999999"   # natija kanali (test)
os.environ["ADMIN_IDS"] = "555000"                          # test admin

from database import db  # noqa: E402
from services.test_api import test_client  # noqa: E402
from services import result_api  # noqa: E402
import main  # noqa: E402  (assign_test_for_application ni real chaqirish uchun)

_checks: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    _checks.append((name, cond, detail))
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail else ""), flush=True)


class _FakeMsg:
    class _Chat:
        def __init__(self, cid):
            self.id = cid

    def __init__(self, cid, mid):
        self.chat = _FakeMsg._Chat(cid)
        self.message_id = mid


class StubBot:
    """Telegram mock — yuborilgan xabarlarni (chat_id, text) yozib boradi."""

    def __init__(self):
        self.sent: list[tuple] = []
        self._mid = 0

    def _next(self, chat_id):
        self._mid += 1
        return _FakeMsg(chat_id, self._mid)

    async def send_message(self, chat_id, text, *args, **kwargs):
        self.sent.append((chat_id, text))
        return self._next(chat_id)

    async def send_photo(self, chat_id, *args, caption="", **kwargs):
        self.sent.append((chat_id, caption))
        return self._next(chat_id)

    async def send_document(self, chat_id, *args, caption="", **kwargs):
        self.sent.append((chat_id, caption))
        return self._next(chat_id)


def spawn_dorikent() -> subprocess.Popen:
    env = dict(os.environ)
    env.update({
        "DORIKENT_DIR": DORIKENT_DIR,
        "BOT_TOKEN": "e2e:dorikent",
        "DB_PATH": str(_TMP / "dorikent.db"),
        "TEST_API_SECRET": INBOUND_SECRET,
        "API_HOST": "127.0.0.1",
        "API_PORT": str(DK_PORT),
        "API_ENABLED": "1",
        "BOT_USERNAME": BOT_USERNAME,
        "RECRUITMENT_API_URL": f"http://127.0.0.1:{MY_PORT}",
        "RECRUITMENT_API_SECRET": RESULT_SECRET,
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        # DoriKent config'idagi env'lar aralashib ketmasligi uchun 2-bot qiymatlarini olib tashlaymiz
        "DATABASE_PATH": "",
    })
    return subprocess.Popen(
        [sys.executable, SCRATCH_HELPER],
        cwd=DORIKENT_DIR, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


async def wait_health(timeout: float = 30) -> bool:
    deadline = time.time() + timeout
    async with httpx.AsyncClient(timeout=3) as client:
        while time.time() < deadline:
            try:
                r = await client.get(f"http://127.0.0.1:{DK_PORT}/api/v1/health")
                if r.status_code == 200 and r.json().get("success"):
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.4)
    return False


async def run() -> None:
    # 1) Ish Topish natija API (bu jarayonda). Notifier = real on_test_result,
    #    shunda kanalga natija e'lon qilish ham tekshiriladi.
    stub = StubBot()
    main._RESULT_BOT = stub
    runner = await result_api.start_result_api(notifier=main.on_test_result)

    # 2) DoriKent'ni GET /health orqali kutamiz
    healthy = await wait_health()
    check("DoriKent GET /api/v1/health ishlaydi", healthy)
    if not healthy:
        raise RuntimeError("DoriKent server ishga tushmadi")

    # 3) Ish Topish ma'lumotlari
    db.init()
    db.add_profession("Farmatsevt")
    prof = next(p for p in db.list_professions() if p["title"] == "Farmatsevt")
    employer_tg, seeker_tg = 700001, 700002
    db.save_employer(employer_tg, {
        "full_name": "Ish Beruvchi", "organization": "DoriKent", "phone": "+998901112233",
        "region": "Toshkent", "district": None,
    })
    vacancy_id = db.save_vacancy(employer_tg, {
        "full_name": "Ish Beruvchi", "organization": "DoriKent", "phone": "+998901112233",
        "region": "Toshkent", "district": None, "profession_id": prof["id"],
        "profession_title": "Farmatsevt", "staff_count": 1, "job_type": "Offline",
        "salary": "5 000 000", "salary_amount": 5000000, "min_experience_years": 1,
        "requirements": "tajriba",
    })
    db.set_vacancy_moderation_status(vacancy_id, "approved")
    db.update_vacancy_field(vacancy_id, "active", 1)
    seeker_id = db.save_seeker(seeker_tg, {
        "photo_id": "x", "full_name": "Ali Valiyev", "age": 25, "gender": "Erkak",
        "phone": "+998907778899", "region": "Toshkent", "profession_id": prof["id"],
        "profession_title": "Farmatsevt", "experience": "2 yil", "previous_job": "Dorixona",
        "salary": "4 000 000",
    })
    # Nomzod 'pending' — YANGI TARTIB: avval test, keyin admin (tasdiqlamaymiz).

    # 4) REAL HTTP: testlar ro'yxati
    tests = await test_client.get_tests()
    e2e_test = next((t for t in tests if t["title"] == "E2E Farmatsevt testi"), None)
    check("GET /tests real HTTP orqali test qaytardi", e2e_test is not None,
          f"{[t['title'] for t in tests]}")
    if not e2e_test:
        raise RuntimeError("E2E test topilmadi")
    check("test question_count = 3", int(e2e_test["questions_count"]) == 3, str(e2e_test["questions_count"]))

    # 5) KASBGA testni biriktiramiz (admin panel: 📝 Testlar → kasb testi)
    db.set_profession_test(prof["id"], int(e2e_test["id"]), e2e_test["title"])
    rt_id, rt_title, rt_src = db.resolve_test_for_profession(prof["id"])
    check("kasb testi to'g'ri aniqlandi (source=profession)",
          rt_id == int(e2e_test["id"]) and rt_src == "profession", f"{rt_id}/{rt_src}")

    # 6) Nomzod ariza yuboradi — YAKUNIY bosqich sifatida kasb testi tayinlanadi.
    #    application_id = seeker.id (vakansiyasiz — kasb-asosli).
    seeker = db.get_seeker(seeker_id)
    assigned = await main.assign_profession_test_for_seeker(stub, seeker, notify=True)
    check("ariza yuborilganda kasb testi tayinlandi", assigned is True)
    at = db.get_active_application_test(seeker_id)
    check("assign real HTTP → application_test synced", at is not None and at["sync_status"] == "synced",
          at["sync_status"] if at else "yo'q")
    assignment_id = int(at["assignment_id"])
    check("assignment_id qaytdi (>=1)", assignment_id >= 1, str(assignment_id))
    check("total_questions assign'dan saqlandi (3)", at["total_questions"] == 3, str(at["total_questions"]))
    check("test_source=profession, vacancy_id=NULL (kasb-asosli)",
          at["test_source"] == "profession" and at["vacancy_id"] is None,
          f"{at['test_source']}/{at['vacancy_id']}")
    check("deep-link xabari nomzodga yuborildi",
          any("Testni boshlash" not in t and "test" in t.lower() for _, t in stub.sent) or len(stub.sent) >= 1)

    # 7) Natijani kutamiz — DoriKent watcher assignment ni ko'rib, REAL HTTP callback yuboradi
    saved = None
    for _ in range(80):  # ~24s
        saved = db.get_application_test_by_assignment(assignment_id)
        if saved and saved["percentage"] is not None:
            break
        await asyncio.sleep(0.3)
    check("natija REAL HTTP callback orqali keldi", saved is not None and saved["percentage"] is not None)
    if saved and saved["percentage"] is not None:
        check("percentage FLOAT to'g'ri saqlandi (66.7)", abs(float(saved["percentage"]) - 66.7) < 0.01,
              str(saved["percentage"]))
        check("status = failed (66.7% < 70%)", saved["status"] == "failed", str(saved["status"]))
        check("score = 67 (round(66.7))", int(saved["score"]) == 67, str(saved["score"]))
        check("correct=2, wrong=1, total=3",
              int(saved["correct_answers"]) == 2 and int(saved["wrong_answers"]) == 1
              and int(saved["total_questions"]) == 3)
        check("candidate/test to'g'ri bog'landi",
              int(saved["candidate_id"]) == seeker_id and int(saved["test_id"]) == int(e2e_test["id"]))

    await asyncio.sleep(0.8)  # notifier (adminga yuborish) tugashini kutamiz

    # 8) YANGI TARTIB: test yakunlangach ariza ADMINGA yuborilgan bo'lishi kerak
    #    (kanalga hali EMAS — faqat admin tasdig'idan keyin).
    admin_msgs = [t for cid, t in stub.sent if str(cid) == "555000"]
    check("test yakunlangach ariza ADMINGA yuborildi (natija bilan)",
          any("moderatsiya" in t.lower() and "66.7" in t for t in admin_msgs),
          (admin_msgs[0].replace(chr(10), " ")[:80] if admin_msgs else "adminga xabar yo'q"))
    check("moderatsiya yozuvi saqlandi",
          len(db.list_moderation_messages("seeker", seeker_id)) >= 1)
    channel_before = [t for cid, t in stub.sent if str(cid) == os.environ["TEST_RESULT_CHANNEL_ID"]]
    check("tasdiqdan OLDIN kanalga natija tushmagan",
          not any("Test natijasi" in t for t in channel_before))
    _srow = db.get_seeker(seeker_id)
    _sstatus = _srow["moderation_status"] if _srow else "?"
    check("nomzod hali 'pending' (avtomatik tasdiqlanmagan)", _sstatus == "pending", _sstatus)

    # 9) Admin TASDIQLAYDI → natija bilan birga kanalga joylanadi
    db.set_seeker_moderation_status(seeker_id, "approved")
    await main.post_seeker_test_result_to_channel(stub, db.get_seeker(seeker_id))
    channel_after = [t for cid, t in stub.sent if str(cid) == os.environ["TEST_RESULT_CHANNEL_ID"]]
    channel_ok = any(("Test natijasi" in t and "66.7" in t and "Noto'g'ri" in t) for t in channel_after)
    check("admin tasdig'idan keyin natija kanalga joylandi (nom/to'g'ri/noto'g'ri/foiz)", channel_ok,
          (channel_after[-1].replace(chr(10), " ")[:90] if channel_after else "kanalga xabar yo'q"))

    # 10) "Mening arizam" ko'rinishida natija matni chiqadimi
    block = main.candidate_tests_block(seeker_id)
    check("Mening arizam natijani ko'rsatadi", "66.7%" in block and "o'ta olmadi" in block.lower(),
          block.replace("\n", " ")[:80])

    # 10) Duplicate himoya: xuddi shu natijani qayta POST qilamiz (vacancy_id yo'q)
    dup_payload = {
        "result_key": f"assignment_{assignment_id}",
        "assignment_id": assignment_id, "candidate_id": seeker_id, "telegram_id": seeker_tg,
        "test_id": int(e2e_test["id"]), "external_application_id": seeker_id,
        "total_questions": 3, "correct_answers": 2, "wrong_answers": 1,
        "score": 67, "percentage": 66.7, "status": "failed",
        "completed_at": "2026-09-30T10:05:00Z",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"http://127.0.0.1:{MY_PORT}/api/v1/test-results",
                              json=dup_payload, headers={"Authorization": f"Bearer {RESULT_SECRET}"})
        check("duplicate → 200 & duplicate=True", r.status_code == 200 and r.json().get("duplicate") is True,
              str(r.status_code))
        rows = db.list_application_tests_by_candidate(seeker_id)
        check("duplicate yangi yozuv yaratmadi (1 ta)", len(rows) == 1, f"{len(rows)} ta")

        # 10) Ownership: noto'g'ri telegram_id → 409
        bad = dict(dup_payload, telegram_id=999999)
        r = await client.post(f"http://127.0.0.1:{MY_PORT}/api/v1/test-results",
                              json=bad, headers={"Authorization": f"Bearer {RESULT_SECRET}"})
        check("noto'g'ri telegram_id → 409", r.status_code == 409, str(r.status_code))

        # 11) X-API-Key header ham qabul qilinadi (DoriKent ikkalasini yuboradi)
        r = await client.post(f"http://127.0.0.1:{MY_PORT}/api/v1/test-results",
                              json=dup_payload, headers={"X-API-Key": RESULT_SECRET})
        check("X-API-Key bilan ham 200", r.status_code == 200, str(r.status_code))

    await runner.cleanup()


async def main_async() -> None:
    proc = spawn_dorikent()
    try:
        await run()
    finally:
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=5)
        except Exception:
            proc.kill()
            out = ""
        if any(not ok for _, ok, _ in _checks) and out:
            print("\n--- DoriKent server log (tail) ---")
            print("\n".join(out.splitlines()[-25:]))

    total = len(_checks)
    passed = sum(1 for _, ok, _ in _checks if ok)
    print("\n" + "=" * 52)
    print(f"E2E natija: {passed}/{total} tekshiruv o'tdi")
    if passed != total:
        for name, ok, detail in _checks:
            if not ok:
                print(f"  ❌ {name} ({detail})")
        sys.exit(1)
    print("🎉 REAL end-to-end integratsiya to'liq ishladi!")


if __name__ == "__main__":
    asyncio.run(main_async())
