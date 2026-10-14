#!/usr/bin/env python3
"""Fetch public HTML evidence into a private trial bundle. No model calls.

The input contains trusted HTTPS source URLs and literal short excerpts. A source
is usable only when its excerpt is found in the newly fetched visible text.
Sources that fail are removed together with questions depending on them.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_HTML_BYTES = 5_000_000
USER_AGENT = "AskResearchReader/0.1 (+https://github.com/maxwelles666/ask)"


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u200b", "")).strip()


class VisibleText(HTMLParser):
    SKIP = {"script", "style", "svg", "nav", "header", "footer", "aside",
            "form", "noscript", "template"}
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool, bool]] = []
        self.all_parts: list[str] = []
        self.main_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        parent_hidden = self.stack[-1][1] if self.stack else False
        parent_main = self.stack[-1][2] if self.stack else False
        hidden = (parent_hidden or tag in self.SKIP or "hidden" in values
                  or values.get("aria-hidden") == "true")
        main = parent_main or tag in {"main", "article"} or values.get("role") == "main"
        if tag not in self.VOID:
            self.stack.append((tag, hidden, main))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in self.VOID:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self.stack and self.stack[-1][1]:
            return
        value = data.strip()
        if value:
            self.all_parts.append(value)
            if self.stack and self.stack[-1][2]:
                self.main_parts.append(value)


def fetch_source(source: dict, max_chars: int, timeout: float) -> dict:
    parsed = urlparse(source["url"])
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("invalid_https_url")
    request = Request(source["url"], headers={
        "User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"
    })
    with urlopen(request, timeout=timeout) as response:
        final_url = response.geturl()
        if urlparse(final_url).scheme != "https":
            raise ValueError("insecure_redirect")
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise ValueError("unsupported_content_type")
        raw = response.read(MAX_HTML_BYTES + 1)
        if len(raw) > MAX_HTML_BYTES:
            raise ValueError("source_too_large")
        charset = response.headers.get_content_charset() or "utf-8"
        try:
            html = raw.decode(charset, errors="replace")
        except LookupError:
            raise ValueError("unknown_character_encoding") from None
    parser = VisibleText()
    parser.feed(html)
    excerpt = normalized(source["text"])
    candidates = [normalized(" ".join(parser.main_parts)),
                  normalized(" ".join(parser.all_parts))]
    document = next((text for text in candidates if excerpt in text), None)
    if document is None:
        raise ValueError("seed_excerpt_not_found")
    if len(document) < len(excerpt) + 200:
        raise ValueError("insufficient_body_text")
    position = document.index(excerpt)
    start = max(0, position - 3500)
    if len(document) - start < max_chars:
        start = max(0, len(document) - max_chars)
    selected = document[start:start + max_chars]
    if excerpt not in selected:
        raise ValueError("excerpt_outside_selected_body")
    now = datetime.now(timezone.utc).isoformat()
    result = dict(source)
    result.update(text=selected, retrieved_at=now, accessed_at=now,
                  content_sha256=hashlib.sha256(selected.encode("utf-8")).hexdigest(),
                  fetched_url=final_url, evidence_scope="fetched_body_excerpt",
                  seed_excerpt=source["text"], body_total_characters=len(document),
                  body_selected_start=start, body_selected_characters=len(selected))
    result["fetch_note"] = "Newly fetched visible HTML; bounded body excerpt located using the seed quote."
    return result


def prepare(seed: dict, max_chars: int = 12000, timeout: float = 20,
            browser_cache: dict | None = None) -> dict:
    successes: dict[str, dict] = {}
    failures: list[dict] = []
    # An explicit cache can contain source text already retrieved by a trusted
    # browser tool when a publisher rejects direct automated HTTP requests.
    # It must preserve the original URL, timestamp and literal seed excerpt.
    cached = {item["id"]: item for item in (browser_cache or {}).get("sources", [])}
    for source in seed["sources"]:
        item = cached.get(source["id"])
        if item is None:
            continue
        text = item.get("text", "")
        if (item.get("url") != source["url"] or source["text"] not in text
                or not len(source["text"]) + 200 <= len(text) <= max_chars
                or item.get("evidence_scope") not in {"browser_fetched_body_excerpt", "fetched_body_excerpt"}):
            raise ValueError("invalid_browser_cache_entry")
        stamp = datetime.fromisoformat(item["retrieved_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("invalid_cache_timestamp")
        age = (datetime.now(timezone.utc) - stamp).total_seconds()
        if not -60 <= age <= 86400:
            raise ValueError("stale_browser_cache_entry")
        combined = dict(source)
        combined.update(item)
        combined["content_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        combined["fetch_note"] = "Previously fetched official URL; trusted private bounded text cache. See evidence_scope for retrieval method."
        successes[source["id"]] = combined
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_source, source, max_chars, timeout): source["id"]
                   for source in seed["sources"] if source["id"] not in successes}
        for future in as_completed(futures):
            sid = futures[future]
            try:
                successes[sid] = future.result()
            except HTTPError as exc:
                failures.append({"source_id": sid, "reason": "http_" + str(exc.code)})
            except (URLError, TimeoutError, OSError):
                failures.append({"source_id": sid, "reason": "network_error"})
            except ValueError as exc:
                failures.append({"source_id": sid, "reason": str(exc)})
    result = dict(seed)
    result.update(kind="prepared_source_bundle", requires_refetch_before_live=False,
                  prepared_at=datetime.now(timezone.utc).isoformat(),
                  note="Private freshly fetched evidence bundle; not model-generated reading cards.")
    result["sources"] = [successes[source["id"]] for source in seed["sources"]
                         if source["id"] in successes]
    result["questions"] = [question for question in seed["questions"]
                           if set(question["source_ids"]) <= successes.keys()]
    result["source_failures"] = sorted(failures, key=lambda item: item["source_id"])
    result["removed_question_ids"] = [question["id"] for question in seed["questions"]
                                      if question not in result["questions"]]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--output", required=True, help="Private JSON evidence bundle path")
    parser.add_argument("--browser-cache", "--source-cache", dest="browser_cache",
                        help="Optional trusted private text cache from direct HTTP or a browser tool")
    parser.add_argument("--max-chars", type=int, default=12000)
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()
    if not 1000 <= args.max_chars <= 30000 or not 1 <= args.timeout <= 30:
        parser.error("max-chars must be 1000–30000 and timeout 1–30 seconds")
    seed = json.loads(Path(args.seed).read_text(encoding="utf-8-sig"))
    cache = (json.loads(Path(args.browser_cache).read_text(encoding="utf-8-sig"))
             if args.browser_cache else None)
    result = prepare(seed, args.max_chars, args.timeout, cache)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    print(json.dumps({"sources": len(result["sources"]), "questions": len(result["questions"]),
                      "failures": result["source_failures"]}, ensure_ascii=False))
    return 0 if result["questions"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
