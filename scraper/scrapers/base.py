import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Browser, Page, Playwright

load_dotenv()

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    def __init__(self, company: str, lessor: str):
        self.company = company
        self.lessor = lessor
        self._playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    async def start(self, headless: bool = True):
        # PLAYWRIGHT_BROWSERS_PATH env var is read automatically by Playwright.
        # Setting it here as a fallback ensures it's applied even if the env
        # was loaded after process start (e.g. via python-dotenv).
        browsers_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
        if browsers_path:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path

        self._playwright = await async_playwright().start()
        # --no-sandbox / --disable-dev-shm-usage: required for Chromium in Docker
        self.browser = await self._playwright.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        self.page = await self.browser.new_page()

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()

    @abstractmethod
    async def login(self) -> bool:
        pass

    @abstractmethod
    async def query(self, containers: list[str], region: str, depot: Optional[str] = None) -> list[dict]:
        pass

    async def cancel(self, items: list[dict], region: str) -> list[dict]:
        # 미지원 임대사는 NotImplementedError → 라우터가 501로 변환.
        raise NotImplementedError(f"{self.lessor} cancel not implemented")

    async def status_detail(self, containers: list[str]) -> list[dict]:
        # Status 탭 단독 조회 — FLOR 만 구현 (precleared 행 enrichment 등 용도).
        raise NotImplementedError(f"{self.lessor} status_detail not implemented")

    async def run(
        self,
        containers: list[str],
        region: str,
        depot: Optional[str] = None,
        headless: bool = True,
    ) -> list[dict]:
        try:
            await self.start(headless=headless)
            if not await self.login():
                # 스크래퍼가 _login_error 속성에 구체 사유를 담았으면 그걸 사용.
                # 다른 스크래퍼처럼 속성 없으면 generic 메시지로 폴백.
                detail = getattr(self, "_login_error", None)
                raise RuntimeError(detail or f"{self.lessor} 로그인 실패")
            return await self.query(containers, region, depot)
        finally:
            await self.close()

    async def run_cancel(
        self,
        items: list[dict],
        region: str,
        headless: bool = True,
    ) -> list[dict]:
        try:
            await self.start(headless=headless)
            if not await self.login():
                raise RuntimeError(f"{self.lessor} 로그인 실패")
            return await self.cancel(items, region)
        finally:
            await self.close()

    async def run_status_detail(
        self,
        containers: list[str],
        headless: bool = True,
    ) -> list[dict]:
        try:
            await self.start(headless=headless)
            if not await self.login():
                raise RuntimeError(f"{self.lessor} 로그인 실패")
            return await self.status_detail(containers)
        finally:
            await self.close()


def _normalize_lessor(code: str) -> str:
    """
    카탈로그 변형 코드를 베이스 임대사 코드로 정규화.
    예: TRIT+TRAM → TRIT, GLOD → GOLD, FLOR+DFIC → FLOR, GESE+CROS → GESE
    """
    if not code:
        return code
    # 장금만 GLOD, 흥아는 GOLD — 같은 Touax 사이트
    if code == "GLOD":
        return "GOLD"
    # + 접미사 제거 (TRIT+TRAM, FLOR+DFIC, GESE+CROS 등)
    return code.split("+")[0]


def get_scraper(company: str, lessor: str) -> Optional[BaseScraper]:
    key = _normalize_lessor(lessor)
    # 자격증명 조회용으로도 정규화된 키 사용
    if key == "TEXA":
        from scrapers.texa import TexaScraper
        return TexaScraper(company, key)
    if key == "TRIT":
        from scrapers.trit import TritScraper
        return TritScraper(company, key)
    if key == "GOLD":
        from scrapers.gold import GoldScraper
        return GoldScraper(company, key)
    if key == "FLOR":
        from scrapers.flor import FlorScraper
        return FlorScraper(company, key)
    if key == "GESE":
        from scrapers.gese import GeseScraper
        return GeseScraper(company, key)
    return None
