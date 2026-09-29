# ЛР 1: Добыча корпуса документов


## Тематика корпуса: Информационная безопасность

**Выбранные источники (рассматривался только ru сегмент)**
* [SecurityLab.ru](https://www.securitylab.ru/)
* [Anti-Malware.ru](https://www.anti-malware.ru/)
* [Хакер (xakep.ru)](https://xakep.ru/)
* [Хабр (раздел Информационная безопасность)](https://habr.com/ru/hubs/infosecurity/)
* [Securelist (Лаборатория Касперского)](https://securelist.ru/)


**Почему именно эти источники:**
- Легко проверяются через site:domain.com в Google
- Имеют пагинацию и категории, что удобно для выкачки
- Сочетаются как короткие новости (пример в SecurityLab), так и длинные разборы (Хакер, Securelist)

---

**Что было сделано для анализа корпуса:**
1. Скачали по 20 образцов с каждого источника (итого 100 документов)
2. Разобрали HTML-структуру каждого источника
3. Выделили общую схему хранения в БД
4. Подготовили статистику

---

## 1. Анализ структуры HTML

### 1.1. SecurityLab.ru

| Элемент | Где находится | Коммент |
|---------|---------------|------------|
| Заголовок | `<title>`, `og:title`, `meta[name=title]` | хорошо заполнены |
| Дата | `meta[property="article:published_time"]` | ISO-формат с таймзоной (`2026-09-15T10:29:28+03:00`) |
| Описание | `og:description`, `meta[name=description]` | - |
| Автор | `meta[name=author]` | - |
| Canonical | `<link rel="canonical">` | - |
| Основной текст | `[itemprop=articleBody]` | лучший селектор для будущего парсера |
| Boilerplate | `<header>`, `<footer>`, `.header-banner`, `.social-links`, множество `<nav>`, рекламные блоки (`svad-728x*`), формы подписки, Yandex.Metrika | очень много |

**Вывод по структуре:**  
Полезный контент компактно лежит в `itemprop=articleBody`. Всё остальное - тяжёлый шаблон Битрикса + реклама. Метаданные отличные.

---

### 1.2. Anti-Malware.ru

| Элемент | Где находится | Коммент |
|---------|---------------|------------|
| Заголовок | `<title>`, `og:title` | - |
| Дата | `article:published_time`, `article:modified_time` | - |
| Описание | `og:description`, `meta[name=description]` | - |
| Canonical| `<link rel="canonical">` | - |
| Основной текст | `.field-name-body` | - |
| Boilerplate | `#navbar`, `.region-brand`, боковые блоки, рекламные баннеры, Yandex.Metrika, ... | Очень высокий процент мусора |

**Вывод:**  
Короткие новостные заметки. Полезный текст занимает всего ~2–3% от сырого HTML

---

### 1.3. Xakep.ru

| Элемент | Где находится | Коммент |
|---------|---------------|------------|
| Заголовок | `<title>`, `og:title` | - |
| Дата | В URL (`/2026/04/17/...`) и в RSS-ссылках; в meta почти нет | - |
| Canonical | `<link rel="canonical">` | - |
| Основной текст | `.bdaia-post-content` (предпочтительно) или `article.xmd` | Лучший: `.bdaia-post-content` |
| Boilerplate | Много скриптов, комментарии, опросы, сайдбары | Высокий процент мусора |

**Вывод:**  
Контент хорошо изолирован в `.bdaia-post-content`. Дата публикации лучше брать из URL. Много JS-мусора

---

### 1.4. Хабр

| Элемент | Где находится | Коммент |
|---------|---------------|------------|
| Заголовок | `<title>`, `og:title`, JSON-LD `headline` | Отлично извлекаются |
| Дата | `<time datetime="...">` + JSON-LD `datePublished` | Отлично извлекаются |
| Описание | `og:description` + JSON-LD | - |
| Canonical | `<link rel="canonical">` | - |
| Основной текст | `.article-body` или `.tm-article-presenter__body` | Лучшее: `.article-body` |
| Boilerplate | `.tm-page__sidebar`, `.tm-footer`, комментарии, плейсхолдеры, реклама | Средний процент |

**Вывод:**  
Одна из самых удобных структур. Есть полноценный JSON (`schema.org/Article`). Дата и заголовок надёжно извлекаются

---

### 1.5. Securelist 

| Элемент | Где находится | Коммент |
|---------|---------------|------------|
| Заголовок | `<title>`, `og:title`, JSON-LD | Отлично извлекается |
| Дата | JSON-LD `datePublished` / `dateModified` | Отлично извлекается |
| Ключевые слова | `meta[name=keywords]` | Есть (APT, malware и т.д.) |
| Canonical | `<link rel="canonical">` | - |
| Основной текст | `article` или `.c-article__content` | - |
| Boilerplate | Много header/footer, sidebar, баннеры Kaspersky, комментарии | Средний–высокий процент |

**Вывод:**  
Эталонная структура для research-статей. JSON-LD очень полный. Контент длинный 

---

### Сводная таблица селекторов (для будущего парсера)

| Источник | Основной контент | Дата | Заголовок | Canonical |
|----------|------------------|------|-----------|-----------|
| **SecurityLab** | `[itemprop=articleBody]` | `article:published_time` | `og:title` / `<title>` | `link[rel=canonical]` |
| **Anti-Malware** | `.field-name-body` | `article:published_time` | `og:title` | `link[rel=canonical]` |
| **Xakep** | `.bdaia-post-content` | из URL или JSON-LD | `og:title` | `link[rel=canonical]` |
| **Habr** | `.article-body` | `<time datetime>` / JSON-LD | `og:title` / JSON-LD | `link[rel=canonical]` |
| **Securelist** | `article` / `.c-article__content` | JSON-LD `datePublished` | `og:title` / JSON-LD | `link[rel=canonical]` |

**Общий boilerplate, который нужно вырезать везде:**
- `<script>`, `<style>`, `<noscript>`, `<iframe>`
- `<nav>`, `<header>`, `<footer>`, `<aside>`
- классы: `.banner`, `.ad`, `.ads`, `.social`, `.share`, `.comments`, `.sidebar`, `.promo`, `.related`

---

## 2. Схема БД 

Структура MongoDB ("documents"):
```
{
  "_id": ObjectId,

  "url": "https://...", // UNIQUE
  "source": "habr", // securitylab | antimalware | xakep | habr | securelist

  "title": "<Заголовок>",
  "published_at": ISODate("..."),  // null, если неизвестно
  "fetched_at": ISODate("..."),

  "clean_text": "<извлечённый текст статьи>",
  "content_hash": "<sha256(clean_text)>", // дедуп + инкрементальный обход

  "meta": {  // опиционально
    "author": "...",
    "canonical": "...",
  }
}
```

Индексы:
```
db.documents.createIndex({ url: 1 }, { unique: true })
db.documents.createIndex({ source: 1 })
db.documents.createIndex({ published_at: -1 })
db.documents.createIndex({ content_hash: 1 })
db.documents.createIndex({ source: 1, published_at: -1 })
```

---

## 3. Статистика и оценка

Для сбора статистики на выборке корпуса документов был написан [скрипт get_stats.py](src/get_stats.py). По итогу его работы была получена следующая информация

```
СТАТИСТИКА ПО ВЫБОРКЕ

Источник          N    avg raw  avg clean    ratio
----------------------------------------------------------------------
antimalware      20   106.5 KB    19.7 KB    18.5%
habr             20   175.1 KB    25.7 KB    14.7%
securelist       20   212.8 KB    33.2 KB    15.6%
securitylab      20    92.1 KB    16.8 KB    18.2%
xakep            20   141.8 KB    10.5 KB     7.4%
----------------------------------------------------------------------
ИТОГО           100   145.7 KB    21.2 KB    14.5%

Сумма raw HTML: 14.2 MB
Сумма clean_text: 2.1 MB
Оценка на 1M док.: ~20.2 GB clean_text
```

Пример извлеченный данных из выборки можно посмотреть [в файле corpus_documents.jsonl](src/corpus_documents.jsonl)
