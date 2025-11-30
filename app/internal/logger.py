import logging
import logging.handlers
import pathlib


class logger_class:
    def __init__(self):
        self.logfile_path = pathlib.Path(__file__).parents[2] / "log" / "uvicorn.log"
        self.logger = logging.getLogger("uvicorn.access")
        self.setup_logging()

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

    def info(self, message: str) -> None:
        self.logger.info(message)

    def debug(self, message: str) -> None:
        self.logger.debug(message)

    def warning(self, message: str) -> None:
        self.logger.warning(message)


logger = logger_class()
