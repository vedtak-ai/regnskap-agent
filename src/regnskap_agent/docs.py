from __future__ import annotations

import json
import os
import re
import ssl
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

import certifi


HELP_URL = "https://hjelp.fiken.no"
HELP_INDEX_URL = f"{HELP_URL}/api/hjelpeartikler/fuse-index"
HELP_MARKDOWN_URL = f"{HELP_URL}/api/hjelpeartikler/markdown"
ACCOUNT_HELP_URL = "https://kontohjelp.fiken.no"
ACCOUNT_HELP_DATA_URL = f"{ACCOUNT_HELP_URL}/data/kontoGruppeInfo"
API_DOCS_URL = "https://fiken.no/api/v2/documentation"
DOCS_URL = HELP_URL
USER_AGENT = "regnskap-agent/0.1"
CACHE_TTL_SECONDS = 24 * 60 * 60


def docs_store_path() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "regnskap-agent" / "fiken-docs.jsonl"


def cache_json_path(name: str) -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "regnskap-agent" / name


@dataclass
class DocEntry:
    title: str
    source_url: str
    text: str
    created_at: float


def add_doc(title: str, source_url: str, text: str, path: Path | None = None) -> Path:
    path = path or docs_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = DocEntry(
        title=title.strip() or "Untitled",
        source_url=source_url.strip(),
        text=normalize_text(text),
        created_at=time.time(),
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
    return path


def list_docs(path: Path | None = None) -> list[dict[str, Any]]:
    entries = load_docs(path)
    return [
        {
            "index": i,
            "title": entry.title,
            "source_url": entry.source_url,
            "characters": len(entry.text),
            "created_at": entry.created_at,
        }
        for i, entry in enumerate(entries)
    ]


def search_docs(
    query: str,
    *,
    path: Path | None = None,
    limit: int = 5,
    refresh: bool = False,
    local_only: bool = False,
) -> list[dict[str, Any]]:
    results = search_local_docs(query, path=path, limit=limit)
    if not local_only and os.environ.get("REGNSKAP_DOCS_OFFLINE") != "1":
        results.extend(search_help_articles(query, limit=limit, refresh=refresh))
    return sorted(results, key=lambda item: item["score"], reverse=True)[:limit]


def search_help_articles(query: str, *, limit: int = 5, refresh: bool = False) -> list[dict[str, Any]]:
    terms = tokenize(query)
    if not terms:
        return []
    results: list[dict[str, Any]] = []
    for article in fetch_help_index(refresh=refresh):
        title = str(article.get("tittel") or article.get("title") or "")
        body = article_text(article)
        score = score_text(query, terms, title, body)
        if score <= 0:
            continue
        slug = article_slug(article)
        results.append(
            {
                "score": score,
                "source": "fiken_help",
                "title": title,
                "slug": slug,
                "source_url": help_article_url(slug),
                "snippet": snippet(body, terms),
            }
        )
    return sorted(results, key=lambda item: item["score"], reverse=True)[:limit]


def get_help_article(slug_or_id: str, *, refresh: bool = False) -> dict[str, Any]:
    slug_or_id = slug_or_id.strip()
    if not slug_or_id:
        raise ValueError("Mangler slug eller id.")
    cache_path = cache_json_path(f"help-article-{safe_cache_key(slug_or_id)}.json")
    if not refresh:
        cached = read_fresh_or_stale_json(cache_path)
        if cached is not None:
            return cached
    data = fetch_json(f"{HELP_MARKDOWN_URL}/{quote(slug_or_id)}")
    markdown = str(data.get("markdown", ""))
    article = {
        "source": "fiken_help",
        "slug": slug_or_id,
        "source_url": extract_canonical_url(markdown) or help_article_url(slug_or_id),
        "markdown_url": f"{help_article_url(slug_or_id)}.md",
        "title": extract_markdown_title(markdown) or slug_or_id,
        "markdown": markdown,
    }
    write_json(cache_path, article)
    return article


def context_for_query(
    query: str,
    *,
    limit: int = 2,
    chars: int = 4000,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for result in search_help_articles(query, limit=limit, refresh=refresh):
        slug = str(result.get("slug") or "")
        if not slug:
            continue
        article = get_help_article(slug, refresh=refresh)
        markdown = str(article["markdown"])
        contexts.append(
            {
                "title": article["title"],
                "slug": slug,
                "source_url": article["source_url"],
                "score": result["score"],
                "markdown": markdown[:chars],
                "truncated": len(markdown) > chars,
            }
        )
    return contexts


def search_accounts(
    query: str,
    *,
    org_form: str | None = None,
    limit: int = 8,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    terms = tokenize(query)
    if not terms:
        return []
    org_form = org_form.upper() if org_form else None
    number = next((term for term in terms if term.isdigit()), "")
    results: list[dict[str, Any]] = []
    for group in fetch_account_groups(refresh=refresh):
        group_number = group.get("nummer")
        group_name = str(group.get("navn", ""))
        for account in group.get("kontoer", []):
            allowed_org_forms = [str(value).upper() for value in account.get("kunForOrgForm", [])]
            if org_form and org_form not in allowed_org_forms:
                continue
            metadata = account.get("metaData", {})
            account_number = str(account.get("kontonummer", ""))
            account_name = str(account.get("navn", ""))
            search_words = [str(value) for value in metadata.get("sokeord", [])]
            help_text = clean_help_text(str(metadata.get("hjelpetekst") or ""))
            haystack = " ".join([account_number, account_name, group_name, " ".join(search_words), help_text])
            score = score_account(terms, number, account_number, account_name, group_name, search_words, help_text)
            if score <= 0:
                continue
            results.append(
                {
                    "score": score,
                    "source": "fiken_account_help",
                    "account_number": int(account_number) if account_number.isdigit() else account_number,
                    "account_name": account_name,
                    "group_number": group_number,
                    "group_name": group_name,
                    "source_url": ACCOUNT_HELP_URL,
                    "valid_vat_codes": metadata.get("gyldigeMvakoder", []),
                    "default_vat_code": metadata.get("defaultMvakode"),
                    "default_vat_code_is_none": metadata.get("defaultMvakodeErIngen"),
                    "warning": clean_help_text(str(metadata.get("advarsel") or "")),
                    "snippet": snippet(haystack, terms),
                }
            )
    return sorted(results, key=lambda item: item["score"], reverse=True)[:limit]


def search_local_docs(query: str, *, path: Path | None = None, limit: int = 5) -> list[dict[str, Any]]:
    terms = tokenize(query)
    if not terms:
        return []
    results: list[dict[str, Any]] = []
    for entry in load_docs(path):
        title_terms = tokenize(entry.title)
        for chunk in chunk_text(entry.text):
            chunk_terms = tokenize(chunk)
            if not chunk_terms:
                continue
            score = sum(3 for term in terms if term in title_terms)
            score += sum(chunk_terms.count(term) for term in terms)
            if score <= 0:
                continue
            results.append(
                {
                    "score": score,
                    "source": "local_cache",
                    "title": entry.title,
                    "source_url": entry.source_url,
                    "snippet": snippet(chunk, terms),
                }
            )
    return sorted(results, key=lambda item: item["score"], reverse=True)[:limit]


def load_docs(path: Path | None = None) -> list[DocEntry]:
    path = path or docs_store_path()
    if not path.exists():
        return []
    entries: list[DocEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        entries.append(
            DocEntry(
                title=str(data.get("title", "")),
                source_url=str(data.get("source_url", "")),
                text=str(data.get("text", "")),
                created_at=float(data.get("created_at", 0)),
            )
        )
    return entries


def fetch_help_index(*, refresh: bool = False) -> list[dict[str, Any]]:
    path = cache_json_path("fiken-help-index.json")
    if not refresh:
        cached = read_fresh_json(path)
        if isinstance(cached, list):
            return cached
    try:
        data = fetch_json(HELP_INDEX_URL)
        if not isinstance(data, list):
            raise ValueError("Fiken help index hadde uventet format.")
        write_json(path, data)
        return data
    except Exception:
        stale = read_fresh_or_stale_json(path)
        if isinstance(stale, list):
            return stale
        raise


def fetch_account_groups(*, refresh: bool = False) -> list[dict[str, Any]]:
    path = cache_json_path("fiken-account-help.json")
    if not refresh:
        cached = read_fresh_json(path)
        if isinstance(cached, list):
            return cached
    try:
        data = fetch_json(ACCOUNT_HELP_DATA_URL)
        if not isinstance(data, list):
            raise ValueError("Fiken kontohjelp hadde uventet format.")
        write_json(path, data)
        return data
    except Exception:
        stale = read_fresh_or_stale_json(path)
        if isinstance(stale, list):
            return stale
        raise


def fetch_json(url: str) -> Any:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    context = ssl.create_default_context(cafile=certifi.where())
    with urlopen(request, timeout=20, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def read_fresh_json(path: Path) -> Any | None:
    if not path.exists() or time.time() - path.stat().st_mtime > CACHE_TTL_SECONDS:
        return None
    return read_fresh_or_stale_json(path)


def read_fresh_or_stale_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_help_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return normalize_text(text)


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-ZæøåÆØÅ0-9_./:-]+", text.lower())


def chunk_text(text: str, size: int = 1100, overlap: int = 160) -> list[str]:
    if len(text) <= size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + size])
        start += size - overlap
    return chunks


def snippet(text: str, terms: list[str]) -> str:
    text = normalize_text(text)
    lower = text.lower()
    positions = [lower.find(term) for term in terms if lower.find(term) >= 0]
    if not positions:
        return text[:500]
    start = max(min(positions) - 180, 0)
    end = min(start + 650, len(text))
    return text[start:end].strip()


def article_slug(article: dict[str, Any]) -> str:
    slug = article.get("slug")
    if isinstance(slug, dict):
        return str(slug.get("current") or article.get("id") or "")
    return str(slug or article.get("id") or "")


def article_text(article: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("tittel", "title", "innledning", "beskrivelse", "innhold", "keyword"):
        value = article.get(key)
        if value:
            parts.append(str(value))
    for title in article.get("innholdsTitler") or []:
        parts.append(str(title))
    return clean_help_text(" ".join(parts))


def help_article_url(slug: str) -> str:
    return f"{HELP_URL}/{slug}" if slug else HELP_URL


def score_text(query: str, terms: list[str], title: str, body: str) -> int:
    score = 0
    title_lower = title.lower()
    body_lower = body.lower()
    query_lower = query.lower()
    if query_lower in title_lower:
        score += 50
    if query_lower in body_lower:
        score += 20
    for term in terms:
        if term in title_lower:
            score += 12
        score += min(body_lower.count(term), 10)
    if all(term in body_lower or term in title_lower for term in terms):
        score += 15
    return score


def score_account(
    terms: list[str],
    number: str,
    account_number: str,
    account_name: str,
    group_name: str,
    search_words: list[str],
    help_text: str,
) -> int:
    score = 0
    account_name_lower = account_name.lower()
    group_name_lower = group_name.lower()
    search_words_lower = [word.lower() for word in search_words]
    help_lower = help_text.lower()
    if number:
        if account_number == number:
            score += 1000
        elif account_number.startswith(number):
            score += 100
    for term in terms:
        if term == account_number:
            score += 1000
        if term in search_words_lower:
            score += 80
        if term in account_name_lower:
            score += 40
        if term in group_name_lower:
            score += 12
        score += min(help_lower.count(term), 8)
    return score


def extract_markdown_title(markdown: str) -> str | None:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
        if line.startswith("title:"):
            return line.split(":", 1)[1].strip().strip('"')
    return None


def extract_canonical_url(markdown: str) -> str | None:
    match = re.search(r"canonical:\s*(https?://\S+)", markdown)
    return match.group(1) if match else None


def safe_cache_key(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value)[:120]
