import asyncio
import logging

from automation.stealth import StealthManager

logger = logging.getLogger("runner")
class Runner:
    def __init__(self, config: dict):
        self.config = config
        self.stealth = StealthManager()

        self.browser = None
        self.page = None
        
    async def start_browser(self, playwright):
        self.browser = await playwright.chromium.launch(headless=False)
        self.page = await self.browser.new_page()
        logger.info("Browser started")


    async def stop(self):
        if self.browser:
            await self.browser.close()
        logger.info("Browser closed")

    async def navigate(self, url: str):
        await self.page.goto(url)
        logger.info(f"Navigated to {url}")

    async def run_loop(self):
        logger.info("Runner started")

        while True:
            try:
                delay = self.stealth.delay_between_tasks()
                await asyncio.sleep(delay)

                # MAIN CYCLE PLACEHOLDER
                logger.info("Running cycle...")

            except Exception as e:
                logger.error(f"Runner error: {e}")
                await asyncio.sleep(2)