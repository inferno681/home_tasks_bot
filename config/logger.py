import logging

from config.config import config


def configure_logging() -> None:
    """Configure the root logging handler and format from config.yaml."""
    logging.basicConfig(
        level=config.logger.level,
        datefmt="%Y-%m-%d %H:%M:%S",
        format=config.logger.format,
    )
