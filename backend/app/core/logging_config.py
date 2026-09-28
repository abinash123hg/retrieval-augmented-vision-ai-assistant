import logging
import sys

CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    global CONFIGURED
    if CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers = [handler]
    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
