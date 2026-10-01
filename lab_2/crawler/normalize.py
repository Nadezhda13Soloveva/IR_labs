from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# пар-ы, не влияющие на содержимое страницы
DROP_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "from",
    "erid",
    "yclid",
    "gclid",
    "fbclid",
    "ysclid",
    "_openstat",
}


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return url

    parsed = urlparse(url)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()

    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    path = parsed.path or "/"
    while "//" in path:
        path = path.replace("//", "/")

    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in DROP_QUERY_KEYS
    ]
    query = urlencode(pairs, doseq=True)

    return urlunparse((scheme, netloc, path, "", query, ""))


def host_of(url: str) -> str:
    return urlparse(url).netloc.lower()


def is_allowed(url: str, allowed_domains: list[str]) -> bool:
    host = host_of(url)
    allowed = {d.lower() for d in allowed_domains}
    if host in allowed:
        return True
    # разрешаем поддомены, если в списке есть родитель
    return any(host.endswith("." + d) for d in allowed)