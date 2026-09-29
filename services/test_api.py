"""DoriKent Test Bot bilan ishlash uchun HTTP API klienti.

MUHIM: bu modul DoriKent botning ma'lumotlar bazasiga HECH QACHON
to'g'ridan-to'g'ri ulanmaydi. Faqat HTTPS API orqali ishlaydi.

Arxitektura:
    2-BOT DB  --HTTPS-->  DoriKent Test API  -->  DoriKent DB
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from config import (
    DORIKENT_TEST_API_SECRET,
    DORIKENT_TEST_API_TIMEOUT,
    DORIKENT_TEST_API_URL,
    dorikent_integration_enabled,
)

logger = logging.getLogger(__name__)


class TestApiError(Exception):
    """DoriKent API bilan ishlashda yuzaga kelgan xato."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class TestApiNotConfigured(TestApiError):
    """Integratsiya .env da sozlanmagan."""


def _first(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Bir nechta mumkin bo'lgan kalitlardan birinchi topilganini qaytaradi."""
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def _normalize_test(item: dict[str, Any]) -> dict[str, Any]:
    """DoriKent test obyektini bir xil ko'rinishga keltirish."""
    return {
        "id": int(_first(item, "id", "test_id")),
        "title": _first(item, "title", "name", "test_title", default="Test"),
        "questions_count": _first(
            item, "questions_count", "question_count", "total_questions", "questions", default=0
        ),
    }


class DoriKentTestClient:
    """DoriKent Test API bilan ishlaydigan asinxron klient."""

    def __init__(
        self,
        base_url: str = DORIKENT_TEST_API_URL,
        secret: str = DORIKENT_TEST_API_SECRET,
        timeout: float = DORIKENT_TEST_API_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.secret = secret
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return dorikent_integration_enabled()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.secret}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.enabled:
            raise TestApiNotConfigured(
                "DoriKent integratsiyasi sozlanmagan (DORIKENT_TEST_API_URL / SECRET yo'q)."
            )
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method, url, headers=self._headers(), **kwargs
                )
        except httpx.TimeoutException as exc:
            raise TestApiError(f"DoriKent API javob bermadi (timeout): {exc}") from exc
        except httpx.HTTPError as exc:
            raise TestApiError(f"DoriKent API ga ulanib bo'lmadi: {exc}") from exc

        if response.status_code >= 400:
            # Maxfiy kalitni logga chiqarmaymiz, faqat status va matn.
            body = response.text[:300]
            raise TestApiError(
                f"DoriKent API xatosi (HTTP {response.status_code}): {body}",
                status_code=response.status_code,
            )
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise TestApiError("DoriKent API JSON qaytarmadi.") from exc

    async def get_tests(self) -> list[dict[str, Any]]:
        """Aktiv testlar ro'yxatini olish: GET /api/v1/tests."""
        data = await self._request("GET", "/api/v1/tests")
        items: list[dict[str, Any]]
        if isinstance(data, dict):
            items = data.get("tests") or data.get("data") or data.get("results") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []
        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                normalized.append(_normalize_test(item))
            except (TypeError, ValueError):
                logger.warning("DoriKent test obyektini o'qib bo'lmadi: %r", item)
        return normalized

    async def assign_test(
        self,
        *,
        candidate_id: int,
        telegram_id: int,
        vacancy_id: int,
        test_id: int,
        external_application_id: int,
    ) -> dict[str, Any]:
        """Testni nomzodga tayinlash: POST /api/v1/test/assign.

        Javob (kutilgan): {"assignment_id": ..., "test_title": ..., "total_questions": ...}
        """
        payload = {
            "candidate_id": candidate_id,
            "telegram_id": telegram_id,
            "vacancy_id": vacancy_id,
            "test_id": test_id,
            "external_application_id": external_application_id,
        }
        data = await self._request("POST", "/api/v1/test/assign", json=payload)
        data = data or {}
        assignment_id = _first(data, "assignment_id", "id")
        if assignment_id is None:
            raise TestApiError("DoriKent assignment_id qaytarmadi.")
        return {
            "assignment_id": int(assignment_id),
            "test_title": _first(data, "test_title", "title", "name"),
            "total_questions": _first(
                data, "total_questions", "questions_count", "question_count"
            ),
            # DoriKent tayyor deep-link qaytarsa — undan foydalanamiz (source of truth).
            "deep_link": _first(data, "deep_link", "deeplink", "url"),
            "raw": data,
        }

    async def get_assignment(self, assignment_id: int) -> dict[str, Any] | None:
        """Tayinlov holatini olish: GET /api/v1/test/assignment/{id}."""
        return await self._request(
            "GET", f"/api/v1/test/assignment/{assignment_id}"
        )

    async def get_result(self, assignment_id: int) -> dict[str, Any] | None:
        """Natijani olish (webhook alternativasi): GET /api/v1/test/result/{id}."""
        return await self._request(
            "GET", f"/api/v1/test/result/{assignment_id}"
        )


# Umumiy klient nusxasi
test_client = DoriKentTestClient()
