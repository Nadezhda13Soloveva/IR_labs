from __future__ import annotations

import argparse
import logging
import sys

from .config import load_config
from .robot import Crawler


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "config",
        help="Путь к YAML-конфигу",
    )
    args = parser.parse_args(argv)

    setup_logging()
    log = logging.getLogger("crawler")

    try:
        cfg = load_config(args.config)
    except Exception as e:
        log.error("Не удалось прочитать конфиг: %s", e)
        return 1

    log.info("Конфиг: %s", args.config)
    log.info("БД: %s / %s", cfg["db"].get("uri"), cfg["db"].get("database"))
    log.info("Delay: %s сек", cfg["logic"]["delay"])

    crawler = Crawler(cfg)
    try:
        crawler.run()
    except KeyboardInterrupt:
        log.warning("Прервано пользователем")
        crawler.close()
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())
