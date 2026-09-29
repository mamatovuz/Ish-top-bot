"""DoriKent Test Bot natijalarini qabul qiluvchi HTTP API server.

DoriKent test tugagach, natijani bu endpointga yuboradi (webhook):
    POST /api/v1/test-results
    Authorization: Bearer <TEST_RESULT_API_SECRET>

Server aiogram polling bilan bir vaqtda, bir event loop ichida ishlaydi.
"""
from __future__ import annotations

import hmac
import logging
from typing import Any, Awaitable, Callable, Optional

from aiohttp import web
from pydantic import BaseModel, Field, ValidationError

from config import RESULT_API_HOST, RESULT_API_PORT, TEST_RESULT_API_SECRET
from database import db

logger = logging.getLogger(__name__)

# main.py da o'rnatiladigan admin-log yozuvchi (ixtiyoriy)
AdminLogger = Callable[[str, Optional[int], str], None]
# Natija saqlangach chaqiriladigan xabar yuboruvchi (ixtiyoriy)
ResultNotifier = Callable[[dict[str, Any], dict[str, Any]], Awaitable[None]]


class TestResultPayload(BaseModel):
    """DoriKent yuboradigan natija tanasi (Pydantic validatsiya).

    Contract eslatmalari (DoriKent `result_sync._build_payload` bilan mos):
      - `percentage` FLOAT bo'lishi mumkin (masalan 66.7) — DoriKent `round(...,1)`.
      - `external_application_id` = 2-botdagi interest_id (correlation uchun).
      - `result_key` = "assignment_<id>" idempotency kaliti (ixtiyoriy, log uchun).
    """

    assignment_id: int
    candidate_id: int
    telegram_id: int
    vacancy_id: Optional[int] = None   # kasb-asosli testlarda vakansiya bo'lmaydi
    test_id: int
    external_application_id: int
    total_questions: int = Field(ge=0)
    correct_answers: int = Field(ge=0)
    wrong_answers: int = Field(ge=0)
    score: float = Field(ge=0)
    percentage: float = Field(ge=0, le=100)
    status: str
    result_key: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


def _authorized(request: web.Request) -> bool:
    """`Authorization: Bearer <secret>` yoki `X-API-Key: <secret>` ni tekshiradi.

    DoriKent (`result_sync._post_result`) ikkala headerni ham yuboradi — shuning
    uchun bu yerda ikkalasi ham qabul qilinadi (constant-time solishtirish bilan)."""
    if not TEST_RESULT_API_SECRET:
        logger.error("TEST_RESULT_API_SECRET o'rnatilmagan — natija API ochiq qoldirilmaydi.")
        return False
    token = ""
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if header.startswith(prefix):
        token = header[len(prefix):].strip()
    if not token:
        token = (request.headers.get("X-API-Key", "") or "").strip()
    if not token:
        return False
    # Vaqt-hujumga chidamli solishtirish
    return hmac.compare_digest(token, TEST_RESULT_API_SECRET)


def create_app(
    *,
    admin_log: Optional[AdminLogger] = None,
    notifier: Optional[ResultNotifier] = None,
) -> web.Application:
    app = web.Application()

    def log_event(event: str, target_id: int | None, details: str) -> None:
        logger.info("%s %s %s", event, target_id, details)
        if admin_log is not None:
            try:
                admin_log(event, target_id, details)
            except Exception:  # noqa: BLE001 - log yozish botni to'xtatmasin
                logger.exception("Admin logga yozib bo'lmadi")

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def receive_result(request: web.Request) -> web.Response:
        if not _authorized(request):
            log_event("TEST_RESULT_INVALID", None, "Noto'g'ri yoki yo'q secret")
            return web.json_response({"error": "unauthorized"}, status=401)

        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return web.json_response({"error": "invalid_json"}, status=400)

        try:
            payload = TestResultPayload.model_validate(body)
        except ValidationError as exc:
            log_event("TEST_RESULT_INVALID", None, f"Validatsiya xatosi: {exc.error_count()} ta")
            return web.json_response(
                {"error": "validation_error", "details": exc.errors()}, status=422
            )

        # ── Ownership / moslik tekshiruvi ──
        row = db.get_application_test_by_assignment(payload.assignment_id)
        if row is None:
            log_event(
                "TEST_RESULT_INVALID",
                payload.assignment_id,
                "assignment topilmadi",
            )
            return web.json_response({"error": "assignment_not_found"}, status=404)

        mismatches: list[str] = []
        if int(row["candidate_id"]) != payload.candidate_id:
            mismatches.append("candidate_id")
        # vacancy_id ixtiyoriy — faqat ikkala tomonda ham bo'lsa solishtiramiz.
        if (
            payload.vacancy_id is not None
            and row["vacancy_id"] is not None
            and int(row["vacancy_id"]) != payload.vacancy_id
        ):
            mismatches.append("vacancy_id")
        if int(row["test_id"]) != payload.test_id:
            mismatches.append("test_id")
        if int(row["telegram_id"]) != payload.telegram_id:
            mismatches.append("telegram_id")
        if int(row["application_id"]) != payload.external_application_id:
            mismatches.append("external_application_id")
        if payload.correct_answers + payload.wrong_answers > payload.total_questions:
            mismatches.append("answers_sum")
        if mismatches:
            log_event(
                "TEST_RESULT_INVALID",
                payload.assignment_id,
                "Mos kelmadi: " + ", ".join(mismatches),
            )
            return web.json_response(
                {"error": "mismatch", "fields": mismatches}, status=409
            )

        # ── Duplicate tekshiruvi (idempotent update) ──
        already_completed = row["status"] in ("completed", "passed", "failed")
        if already_completed:
            log_event(
                "TEST_RESULT_DUPLICATE",
                payload.assignment_id,
                f"Takroriy natija, mavjudi yangilanadi (candidate={payload.candidate_id})",
            )

        result_status = "passed" if payload.status.lower() in ("passed", "pass", "1", "true") else (
            "failed" if payload.status.lower() in ("failed", "fail", "0", "false") else payload.status
        )
        db.save_test_result(
            payload.assignment_id,
            {
                "total_questions": payload.total_questions,
                "correct_answers": payload.correct_answers,
                "wrong_answers": payload.wrong_answers,
                "score": payload.score,
                "percentage": payload.percentage,
                "result_status": result_status,
                "status": result_status if result_status in ("passed", "failed") else "completed",
                "started_at": payload.started_at,
                "completed_at": payload.completed_at,
            },
        )
        log_event(
            "TEST_RESULT_RECEIVED",
            payload.assignment_id,
            f"candidate={payload.candidate_id} {payload.percentage}% ({result_status})",
        )

        if notifier is not None:
            saved = db.get_application_test_by_assignment(payload.assignment_id)
            try:
                await notifier(dict(saved) if saved else {}, payload.model_dump())
            except Exception:  # noqa: BLE001
                logger.exception("Natija haqida xabar yuborib bo'lmadi")

        return web.json_response({"status": "ok", "duplicate": already_completed})

    app.router.add_get("/health", health)
    app.router.add_post("/api/v1/test-results", receive_result)
    return app


async def start_result_api(
    *,
    admin_log: Optional[AdminLogger] = None,
    notifier: Optional[ResultNotifier] = None,
) -> web.AppRunner:
    """Natija API serverini ishga tushirish. Runner qaytaradi (to'xtatish uchun)."""
    app = create_app(admin_log=admin_log, notifier=notifier)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, RESULT_API_HOST, RESULT_API_PORT)
    await site.start()
    logger.info(
        "Natija API ishga tushdi: http://%s:%s/api/v1/test-results",
        RESULT_API_HOST,
        RESULT_API_PORT,
    )
    return runner
