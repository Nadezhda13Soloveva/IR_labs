from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from bs4 import BeautifulSoup

SOURCE_CONFIG: dict[str, dict] = {
    "securitylab": {
        "content_selectors": ['[itemprop="articleBody"]', "article"],
        "date_meta": ["article:published_time", "og:published_time"],
    },
    "antimalware": {
        "content_selectors": [".field-name-body", ".node-content", "article"],
        "date_meta": ["article:published_time", "og:published_time"],
    },
    "xakep": {
        "content_selectors": [".bdaia-post-content", "article.xmd", "article"],
        "date_meta": ["article:published_time", "og:published_time"],
        "date_from_url": True,
    },
    "habr": {
        "content_selectors": [".article-body", ".tm-article-presenter__body", "main"],
        "date_meta": ["article:published_time"],
        "date_from_time_tag": True,
        "json_ld": True,
    },
    "securelist": {
        "content_selectors": ["article", ".c-article__content"],
        "date_meta": ["article:published_time", "og:published_time"],
        "json_ld": True,
    },
}

FOLDER_TO_SOURCE = {
    "securitylab": "securitylab",
    "antimalware": "antimalware",
    "xakep": "xakep",
    "habr": "habr",
    "habr_infosecurity": "habr",
    "securelist": "securelist",
}

BOILERPLATE_TAGS = (
    "script", "style", "nav", "footer", "header",
    "aside", "form", "iframe", "noscript",
)
BOILERPLATE_CSS = (
    ".banner", ".ad", ".ads", ".advert", ".sidebar", ".menu",
    ".comments", ".social", ".share", ".related", ".promo",
    ".tm-page__sidebar", ".tm-footer", ".wpdiscuz", ".header-banner",
)


def get_meta(soup: BeautifulSoup, key: str) -> Optional[str]:
    tag = soup.find("meta", property=key) or soup.find("meta", attrs={"name": key})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None


def extract_json_ld_article(soup: BeautifulSoup) -> dict:
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except Exception:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data])
        for item in items:
            if not isinstance(item, dict):
                continue
            t = item.get("@type", "")
            types = t if isinstance(t, list) else [t]
            if any(x in ("Article", "NewsArticle", "BlogPosting") for x in types):
                return item
    return {}


def extract_url(soup: BeautifulSoup) -> str:
    can = soup.find("link", rel="canonical")
    if can and can.get("href"):
        return can["href"].strip()
    return get_meta(soup, "og:url") or ""


def extract_published_at(soup: BeautifulSoup, cfg: dict, url: str) -> Optional[str]:
    for key in cfg.get("date_meta", []):
        val = get_meta(soup, key)
        if val:
            return val
    if cfg.get("date_from_time_tag"):
        t = soup.find("time", attrs={"datetime": True})
        if t and t.get("datetime"):
            return t["datetime"]
    if cfg.get("json_ld"):
        ld = extract_json_ld_article(soup)
        for k in ("datePublished", "dateCreated"):
            if ld.get(k):
                return ld[k]
    if cfg.get("date_from_url") and url:
        m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T00:00:00"
    return None


def extract_clean_text(html: str, cfg: dict) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(BOILERPLATE_TAGS):
        tag.decompose()
    for sel in BOILERPLATE_CSS:
        for el in soup.select(sel):
            el.decompose()
    for sel in cfg.get("content_selectors", []):
        el = soup.select_one(sel)
        if el:
            text = re.sub(r"\n{3,}", "\n\n", el.get_text(separator="\n", strip=True))
            if len(text) > 150:
                return text
    body = soup.body or soup
    return re.sub(r"\n{3,}", "\n\n", body.get_text(separator="\n", strip=True))


def process_file(path: Path, folder_name: str) -> tuple[dict[str, Any], dict[str, int]]:
    source = FOLDER_TO_SOURCE.get(folder_name.lower(), folder_name.lower())
    cfg = SOURCE_CONFIG.get(source, {
        "content_selectors": ["article", "main", ".content"],
        "date_meta": ["article:published_time", "og:published_time"],
    })

    raw_bytes = path.read_bytes()
    raw_size = len(raw_bytes)
    html = raw_bytes.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")

    url = extract_url(soup)
    title = get_meta(soup, "og:title") or (
        soup.title.string.strip() if soup.title and soup.title.string else ""
    )
    published = extract_published_at(soup, cfg, url)

    ld = extract_json_ld_article(soup)
    if ld:
        title = title or ld.get("headline") or ""
        published = published or ld.get("datePublished")

    clean_text = extract_clean_text(html, cfg)
    clean_bytes = clean_text.encode("utf-8")
    clean_size = len(clean_bytes)

    doc = {
        "url": url or f"file://{path.name}",
        "source": source,
        "title": title,
        "published_at": published,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "content_hash": hashlib.sha256(clean_bytes).hexdigest(),
        "clean_text": clean_text,
        "meta": {
            "author": get_meta(soup, "author"),
            "canonical": url or None,
        },
    }
    metrics = {
        "raw_size": raw_size,
        "clean_size": clean_size,
        "clean_chars": len(clean_text),
    }
    return doc, metrics


def human(n: float) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {u}" if u != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def print_stats(rows: list[tuple[str, dict]]) -> None:
    by_src: dict[str, list] = defaultdict(list)
    for source, m in rows:
        by_src[source].append(m)

    print("СТАТИСТИКА ПО ВЫБОРКЕ")
    print(f"\n{'Источник':<14} {'N':>4} {'avg raw':>10} {'avg clean':>10} {'ratio':>8}")
    print("-" * 70)

    total_raw = total_clean = 0
    n_all = 0
    for src in sorted(by_src):
        items = by_src[src]
        n = len(items)
        raws = [i["raw_size"] for i in items]
        cleans = [i["clean_size"] for i in items]
        avg_raw, avg_clean = sum(raws) / n, sum(cleans) / n
        ratio = avg_clean / avg_raw if avg_raw else 0
        total_raw += sum(raws)
        total_clean += sum(cleans)
        n_all += n
        print(f"{src:<14} {n:>4} {human(avg_raw):>10} {human(avg_clean):>10} {ratio*100:>7.1f}%")

    print("-" * 70)
    print(f"{'ИТОГО':<14} {n_all:>4} {human(total_raw/max(n_all,1)):>10} "
          f"{human(total_clean/max(n_all,1)):>10} "
          f"{(total_clean/total_raw*100 if total_raw else 0):>7.1f}%")
    print(f"\nСумма raw HTML: {human(total_raw)}")
    print(f"Сумма clean_text: {human(total_clean)}")
    if n_all:
        print(f"Оценка на 1M док.: ~{human(total_clean / n_all * 1_000_000)} clean_text")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html-dir", type=Path, default=Path("html"))
    ap.add_argument("--out-jsonl", type=Path, default=Path("corpus_documents.jsonl"))
    ap.add_argument("--stats-only", action="store_true")
    args = ap.parse_args()

    if not args.html_dir.is_dir():
        raise SystemExit(f"Нет каталога: {args.html_dir}")

    docs: list[dict] = []
    metrics_rows: list[tuple[str, dict]] = []

    for sub in sorted(args.html_dir.iterdir()):
        if not sub.is_dir():
            continue
        files = sorted(sub.glob("*.html")) + sorted(sub.glob("*.htm"))
        print(f"[*] {sub.name}: {len(files)} файлов")
        for fp in files:
            try:
                doc, metrics = process_file(fp, sub.name)
                docs.append(doc)
                metrics_rows.append((doc["source"], metrics))
            except Exception as e:
                print(f"ERROR {fp.name}: {e}")

    if not docs:
        raise SystemExit("Документов не найдено")

    print_stats(metrics_rows)

    if not args.stats_only:
        with args.out_jsonl.open("w", encoding="utf-8") as f:
            for d in docs:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()