"""Извлечение ссылок на статьи со страницы"""

from __future__ import annotations

from typing import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .normalize import is_allowed, normalize_url


def extract_links(
    html: str,
    base_url: str,
    *,
    allowed_domains: list[str],
    selectors: list[str],
) -> list[str]:
    """
    достаёт ссылки по css-селекторам, оставляет только allowed_domains
    """
    soup = BeautifulSoup(html, "lxml")
    found: set[str] = set()

    def consider(href: str) -> None:
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            return
        absolute = urljoin(base_url, href)
        normalized = normalize_url(absolute)
        if not normalized.startswith("http"):
            return
        if not is_allowed(normalized, allowed_domains):
            return
        found.add(normalized)

    if selectors:
        for sel in selectors:
            for a in soup.select(sel):
                consider(a.get("href", ""))
    else:
        for a in soup.find_all("a", href=True):
            consider(a["href"])

    return sorted(found)


def looks_like_article(url: str, source: str) -> bool:
    """грубая эвристика: отсечь чисто служебные URL"""
    u = url.lower()
    skip_parts = (
        "/tag/",
        "/tags/",
        "/hubs/",
        "/users/",
        "/search",
        "/login",
        "/register",
        "/feed",
        "/rss",
        "/wp-admin",
        "/wp-json",
        "/#",
    )
    if any(p in u for p in skip_parts):
        return False

    if source == "securitylab":
        return "/news/" in u or "/analytics/" in u
    if source == "antimalware":
        return "/news/" in u or "/analytics/" in u
    if source == "xakep":
        # /2026/04/17/slug/
        return any(f"/{y}/" in u for y in range(2015, 2031))
    if source == "habr":
        return "/articles/" in u or "/news/" in u
    if source == "securelist":
        # статьи обычно /slug/digits/
        return u.rstrip("/").count("/") >= 3 and "securelist.ru" in u

    return True


def filter_article_urls(
    urls: Iterable[str], source: str
) -> list[str]:
    return [u for u in urls if looks_like_article(u, source)]
