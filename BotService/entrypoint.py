import asyncio
import logging
import os

logger = logging.getLogger(__name__)


async def _main():
    from main import main as tg_main

    coros = [tg_main()]

    if os.getenv("VK_GROUP_TOKEN") and os.getenv("VK_GROUP_ID"):
        from vk_bot import run as vk_run
        coros.append(vk_run())
        logger.info("Starting Telegram bot + VK bot")
    else:
        logger.info("VK_GROUP_TOKEN or VK_GROUP_ID not set — starting Telegram bot only")

    await asyncio.gather(*coros)


if __name__ == "__main__":
    asyncio.run(_main())
