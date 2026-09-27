import asyncio
import logging
from app.services.invite_service import invite_service

logger = logging.getLogger("authentik_manager.worker")

class BackgroundWorker:
    def __init__(self, interval_seconds: int = 45):
        self.interval = interval_seconds
        self._task = None
        self._running = False

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Background auto-assignment worker started.")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Background auto-assignment worker stopped.")

    async def _run_loop(self):
        while self._running:
            try:
                redeemed = await invite_service.sync_redemptions()
                if redeemed > 0:
                    logger.info(f"Worker auto-assigned permissions for {redeemed} invited user(s).")
            except Exception as e:
                logger.error(f"Error in background sync worker: {e}")
            
            await asyncio.sleep(self.interval)

worker = BackgroundWorker()
