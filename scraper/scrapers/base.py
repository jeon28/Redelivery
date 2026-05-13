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
    async def query(self, containers: list[str], region: str) -> list[dict]:
        pass

    async def run(self, containers: list[str], region: str, headless: bool = True) -> list[dict]:
        try:
            await self.start(headless=headless)
            if not await self.login():
                raise RuntimeError(f"{self.lessor} 로그인 실패")
            return await self.query(containers, region)
        finally:
            await self.close()


def get_scraper(company: str, lessor: str) -> Optional[BaseScraper]:
    if lessor == "TEXA":
        from scrapers.texa import TexaScraper
        return TexaScraper(company, lessor)
    if lessor == "TRIT":
        from scrapers.trit import TritScraper
        return TritScraper(company, lessor)
    return None
