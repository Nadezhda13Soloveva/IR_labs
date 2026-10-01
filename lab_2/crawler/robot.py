from __future__ import annotations

import hashlib
import logging
import signal
import time
from typing import Any

from .db import Storage
from .fetcher import Fetcher
from .normalize import normalize_url
from .parser_links import extract_links, filter_article_urls

log = logging.getLogger("crawler")


class Crawler:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.logic = cfg["logic"]
        self.sources = cfg["sources"]
        self.storage = Storage(cfg)
        self.fetcher = Fetcher(
            user_agent=self.logic["user_agent"],
            timeout=float(self.logic["timeout"]),
        )
        self._stop = False
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame) -> None:  # noqa: ANN001
        log.warning("Получен сигнал %s - останавливаемся после текущей страницы", signum)
        self._stop = True

    def seed_frontier(self) -> None:
        """очередь пуста - положить стартовые URL"""
        if not self.storage.frontier_empty():
            recovered = self.storage.recover_in_progress()
            if recovered:
                log.info("Восстановлено in_progress → pending: %s", recovered)
            return

        log.info("Frontier пуст - загружаем start_urls")
        for source, scfg in self.sources.items():
            for raw in scfg.get("start_urls", []):
                url = normalize_url(raw)
                self.storage.enqueue(url, source)
                log.info("  seed [%s] %s", source, url)

    def schedule_recrawl(self) -> int:
        """lобавить в очередь устаревшие документы"""
        days = int(self.logic.get("recrawl_after_days", 7))
        if days <= 0:
            return 0
        threshold = int(time.time()) - days * 86400
        stale = self.storage.stale_urls(threshold, limit=200)
        n = 0
        for doc in stale:
            if self.storage.enqueue(
                doc["url"], doc["source"], force_pending=True
            ):
                n += 1
        if n:
            log.info("В очередь на переобход добавлено: %s", n)
        return n

    def _process_one(self, item: dict[str, Any]) -> None:
        url = item["url"]
        source = item["source"]
        scfg = self.sources.get(source, {})
        delay = float(self.logic["delay"])
        max_errors = int(self.logic["max_errors_per_url"])

        existing = self.storage.get_document(url)
        etag = existing.get("etag") if existing else None
        last_modified = existing.get("last_modified") if existing else None
        old_hash = existing.get("content_hash") if existing else None

        log.info("FETCH [%s] %s", source, url)
        time.sleep(delay)

        result = self.fetcher.fetch(url, etag=etag, last_modified=last_modified)

        if not result.ok:
            log.warning("  ошибка: %s", result.error)
            self.storage.mark_error(url, result.error or "unknown", max_errors)
            return

        if result.not_modified:
            log.info("  304 Not Modified")
            self.storage.touch_crawled_at(url)
            self.storage.mark_done(url)
            return

        new_hash = hashlib.sha256(result.body.encode("utf-8", errors="replace")).hexdigest()

        if old_hash and old_hash == new_hash:
            log.info("  содержимое не изменилось (hash)")
            self.storage.touch_crawled_at(url)
            self.storage.mark_done(url)
            return

        # сохраняем / обновляем документ
        self.storage.upsert_document(
            url=url,
            source=source,
            raw_html=result.body,
            content_hash=new_hash,
            etag=result.etag,
            last_modified=result.last_modified,
        )
        log.info(
            "  сохранён html (%s байт), docs=%s",
            len(result.body.encode("utf-8", errors="replace")),
            self.storage.documents_count(),
        )

        # новые ссылки
        links = extract_links(
            result.body,
            url,
            allowed_domains=scfg.get("allowed_domains", []),
            selectors=scfg.get("article_link_selectors", []),
        )
        article_links = filter_article_urls(links, source)
        added = 0
        for link in article_links:
            if self.storage.enqueue(link, source):
                added += 1
        log.info(" новых URL в очереди: %s (из %s ссылок)", added, len(article_links))

        self.storage.mark_done(url)

    def run(self) -> None:
        self.seed_frontier()
        self.schedule_recrawl()

        max_pages = int(self.logic["max_pages"])
        log.info(
            "Старт. documents=%s, pending=%s, max_pages=%s",
            self.storage.documents_count(),
            self.storage.pending_count(),
            max_pages,
        )

        while not self._stop:
            if self.storage.documents_count() >= max_pages:
                log.info("Достигнут max_pages=%s — стоп", max_pages)
                break

            item = self.storage.claim_next_pending()
            if item is None:
                # возможно, появились stale
                if self.schedule_recrawl() == 0:
                    log.info("Очередь пуста — работа завершена")
                    break
                continue

            try:
                self._process_one(item)
            except Exception as e:
                log.exception("Сбой на %s: %s", item.get("url"), e)
                self.storage.mark_error(
                    item["url"],
                    str(e),
                    int(self.logic["max_errors_per_url"]),
                )

        log.info(
            "Остановка. documents=%s, pending=%s",
            self.storage.documents_count(),
            self.storage.pending_count(),
        )
        self.close()

    def close(self) -> None:
        self.fetcher.close()
        self.storage.close()
