import asyncio
import logging
import sys

from bot.core import bot, setup_dispatcher
from dlbot.utils.helpers import check_dependencies

async def main():
    """
    The main function to start the bot.
    """
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        stream=sys.stdout,
    )
    logger = logging.getLogger(__name__)

    # Check for system dependencies like ffmpeg
    logger.info("Checking system dependencies...")
    if not check_dependencies():
        logger.error("A required system dependency is missing. Please install it and try again.")
        sys.exit(1)

    # Set up the dispatcher and include all routers
    dp = setup_dispatcher()

    logger.info("Starting bot polling...")
    # Start polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
