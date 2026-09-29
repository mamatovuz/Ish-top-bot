"""E2E uchun DoriKent Test Bot serverini (REAL kod) subprocess sifatida ishga tushiradi.

Telegram qatlami mock qilinadi: nomzod savollarga javob berish o'rniga,
watcher yangi assignment ni ko'rib, DoriKent'ning REAL result-saqlash +
REAL HTTP sync kodidan foydalanib natijani 2-botga yuboradi (66.7% -> failed).

Bu skript DORIKENT repo'siga tegmaydi — uni sys.path orqali import qiladi.
"""
import asyncio
import os
import sys

DORIKENT = os.environ["DORIKENT_DIR"]
# DoriKent modullari (config, db, api, services) shu yo'ldan import qilinsin.
sys.path.insert(0, DORIKENT)

import config  # noqa: E402  (DoriKent config)
import db  # noqa: E402       (DoriKent db)
import services.result_sync as result_sync  # noqa: E402
from api.app import create_app  # noqa: E402
import uvicorn  # noqa: E402

# Determinstik natija: 3 savoldan 2 to'g'ri -> 66.7% -> passed=0 (pass=70%).
TOTAL, CORRECT, WRONG = 3, 2, 1


async def seed_test() -> int:
    await db.init_db()
    tid = await db.create_test("E2E Farmatsevt testi", TOTAL, 70, 1, 1, 1)
    await db.update_test_field(tid, "is_active", 1)
    for i in range(TOTAL):
        await db.add_question(tid, f"E2E savol {i + 1}?", "To'g'ri javob", ["Xato 1", "Xato 2"])
    return tid


async def auto_finish_watcher() -> None:
    """Yangi (assigned) recruitment assignment ni ko'rib, REAL natija saqlaydi
    va REAL HTTP sync orqali 2-botga yuboradi (Telegram UI o'rniga)."""
    seen: set[int] = set()
    while True:
        try:
            conn = await db.get_db()
            async with conn.execute(
                "SELECT * FROM test_assignments WHERE status='assigned'"
            ) as cur:
                rows = await cur.fetchall()
            for a in rows:
                if a["id"] in seen:
                    continue
                seen.add(a["id"])
                percent = round(CORRECT / TOTAL * 100, 1)  # 66.7
                passed = 1 if percent >= 70 else 0
                rid = await db.save_recruitment_result(
                    telegram_id=a["telegram_id"],
                    test_id=a["test_id"],
                    total=TOTAL,
                    correct=CORRECT,
                    wrong=WRONG,
                    percent=percent,
                    passed=passed,
                    candidate_id=a["candidate_id"],
                    vacancy_id=a["vacancy_id"],
                    assignment_id=a["id"],
                    external_application_id=a["external_application_id"],
                    started_at="2026-09-30 10:00:00",
                    completed_at="2026-09-30 10:05:00",
                )
                await db.set_assignment_completed(a["id"], rid)
                # REAL HTTP sync (retry loop ham himoya sifatida ishlaydi)
                await result_sync.send_result_now(rid)
        except Exception as exc:  # noqa: BLE001
            print("watcher xatosi:", type(exc).__name__, exc, flush=True)
        await asyncio.sleep(0.3)


async def main() -> None:
    result_sync._LOOP_INTERVAL = 1  # testda tez sync
    await seed_test()
    app = create_app()
    cfg = uvicorn.Config(
        app, host=config.API_HOST, port=config.API_PORT,
        log_level="warning", access_log=False,
    )
    server = uvicorn.Server(cfg)
    server.install_signal_handlers = lambda: None
    print(f"DORIKENT E2E server: http://{config.API_HOST}:{config.API_PORT}", flush=True)
    await asyncio.gather(
        server.serve(),
        result_sync.run_sync_loop(),
        auto_finish_watcher(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
