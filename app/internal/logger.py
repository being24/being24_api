import json
import logging
import logging.handlers
import os
import pathlib

import requests
from dotenv import load_dotenv


class logger_class:
    def __init__(self):
        self.root_path = pathlib.Path(__file__).parents[2]
        self.logfile_path = self.root_path / "log" / "uvicorn.log"
        self.env_path = self.root_path / ".env"

        self.logger = logging.getLogger("uvicorn.access")
        self.setup_logging()
        load_dotenv(self.env_path)

        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
        if not self.webhook_url:
            self.logger.warning("DISCORD_WEBHOOK_URL is not set in .env file")

    def setup_logging(self):
        # Ensure log directory exists
        self.logfile_path.parent.mkdir(parents=True, exist_ok=True)

        # Setup uvicorn.access logger
        logger = logging.getLogger("uvicorn.access")
        logger.setLevel(logging.WARNING)

        # Rotating file handler
        handler = logging.handlers.RotatingFileHandler(
            filename=self.logfile_path,
            encoding="utf-8",
            maxBytes=32 * 1024,  # 32 KiB
            backupCount=5,  # Rotate through 5 files
        )
        dt_fmt = "%Y-%m-%d %H:%M:%S"
        formatter = logging.Formatter(
            "[{asctime}] [{levelname:<8}] {name}: {message}", dt_fmt, style="{"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Setup uvicorn logger
        logger = logging.getLogger("uvicorn")
        logger.setLevel(logging.WARNING)

        # Setup uvicorn.error logger
        logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

    def error(self, message: str) -> None:
        self.logger.error(message)
        self.send_to_webhook(level="ERROR", message=message)

    def info(self, message: str) -> None:
        self.logger.info(message)
        self.send_to_webhook(level="INFO", message=message)

    def debug(self, message: str) -> None:
        self.logger.debug(message)
        self.send_to_webhook(level="DEBUG", message=message)

    def warning(self, message: str) -> None:
        self.logger.warning(message)
        self.send_to_webhook(level="WARNING", message=message)

    def send_to_webhook(self, level: str, message: str) -> None:
        """Send a log entry to Discord webhook.

        Parameters
        ----------
        level: str
            Log level label to include in the message (e.g., INFO, ERROR).
        message: str
            Log message content.
        """
        if not self.webhook_url:
            return

        level_upper = level.upper()
        content = f"{level_upper}\n{message}"

        headers = {"Content-Type": "application/json"}
        data = {"content": content}
        try:
            response = requests.post(
                self.webhook_url, data=json.dumps(data), headers=headers
            )
            if response.status_code != 204:
                self.logger.warning(
                    f"Failed to send log to Discord webhook: {response.status_code} {response.text}"
                )
        except Exception as e:
            self.logger.warning(f"Exception occurred while sending webhook: {e}")


logger = logger_class()
