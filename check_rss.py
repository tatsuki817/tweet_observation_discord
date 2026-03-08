#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.request
from typing import List, Optional, Tuple

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

STATE_FILE = "state.json"
DEFAULT_DISCORD_USERNAME = "X通知Bot"
TARGET_USERNAME = "F3yT8"
DISCORD_CONTENT_LIMIT = 2000
LOG_TEXT_LIMIT = 300
DEBUG_HTML_PREVIEW_LIMIT = 500
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
ACCEPT_LANGUAGE = "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7"


def _extract_status_urls_from_hrefs(hrefs: List[str], username: str) -> List[str]:
    pattern = re.compile(rf"/{re.escape(username)}/status/(\d+)", re.IGNORECASE)
    hits: List[str] = []

    for href in hrefs:
        match = pattern.search(href)
        if not match:
            continue
        status_url = f"https://x.com/{username}/status/{match.group(1)}"
        if status_url not in hits:
            hits.append(status_url)

    return hits


def _normalize_text(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _truncate_for_discord(message: str) -> str:
    return _truncate_text(message, DISCORD_CONTENT_LIMIT)


def _new_context(browser):
    return browser.new_context(
        user_agent=BROWSER_USER_AGENT,
        locale="ja-JP",
        timezone_id="Asia/Tokyo",
        viewport={"width": 1366, "height": 768},
        extra_http_headers={"Accept-Language": ACCEPT_LANGUAGE},
    )


def fetch_latest_status_url(username: str) -> Tuple[str, str, str, int]:
    target_url = f"https://x.com/{username}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = _new_context(browser)
        page = context.new_page()

        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)

        page_title = page.title()
        current_url = page.url
        hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href') || '')")

        status_urls = _extract_status_urls_from_hrefs(hrefs, username)
        hit_count = len(status_urls)

        if hit_count == 0:
            print(f"DEBUG: page title: {page_title}")
            print(f"DEBUG: page url: {current_url}")
            print(f"DEBUG: status link candidates: {hit_count}")
            browser.close()
            raise ValueError("statusリンクを抽出できませんでした")

        latest_status_url = status_urls[0]
        browser.close()
        return latest_status_url, page_title, current_url, hit_count


def _is_noise_line(line: str) -> bool:
    lower = line.lower().strip()
    if not lower:
        return True
    if lower in {f"@{TARGET_USERNAME.lower()}", "show more", "translate post"}:
        return True
    if lower in {"reply", "repost", "like", "bookmark", "share"}:
        return True
    if re.fullmatch(r"[\d,\.]+", lower):
        return True
    if re.fullmatch(r"\d+[kmb]?", lower):
        return True
    if re.search(r"(am|pm|午前|午後)", lower) and re.search(r"\d", lower):
        return True
    if re.search(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}", lower):
        return True
    if re.search(r"\d+\s*(reply|repost|like|bookmark|view|表示)", lower):
        return True
    return False


def _extract_text_from_article_fallback(article_texts: List[str]) -> Optional[str]:
    candidates: List[str] = []
    for idx, raw in enumerate(article_texts, start=1):
        normalized = _normalize_text(raw)
        lines = [ln.strip() for ln in normalized.splitlines() if ln.strip()]
        cleaned_lines = [ln for ln in lines if not _is_noise_line(ln)]
        candidate = _normalize_text("\n".join(cleaned_lines))
        if candidate:
            candidates.append(candidate)
            print(f"DEBUG: article fallback candidate[{idx}]: {_truncate_text(candidate, 120)}")
        else:
            print(f"DEBUG: article fallback candidate[{idx}]: <empty>")

    if not candidates:
        return None

    # 最も自然で長い候補を採用
    candidates.sort(key=lambda x: len(x), reverse=True)
    return candidates[0]


def fetch_post_text(status_url: str) -> Optional[str]:
    selectors = [
        'article [data-testid="tweetText"]',
        'div[data-testid="tweetText"]',
        'article div[lang]',
        'main article div[lang]',
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = _new_context(browser)
        page = context.new_page()

        print(f"DEBUG: open status page: {status_url}")
        page.goto(status_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(7000)

        print(f"DEBUG: status page title: {page.title()}")
        print(f"DEBUG: status page url: {page.url}")
        html_preview = _truncate_text(page.content().replace("\n", " "), DEBUG_HTML_PREVIEW_LIMIT)
        print(f"DEBUG: status page html preview: {html_preview}")

        for selector in selectors:
            texts = page.eval_on_selector_all(selector, "els => els.map(e => (e.innerText || '').trim())")
            if not texts:
                print(f"DEBUG: tweet text selector no hit: {selector}")
                continue

            merged_text = _normalize_text("\n".join([t for t in texts if t.strip()]))
            if merged_text:
                print(f"DEBUG: tweet text selector hit: {selector}")
                return merged_text

            print(f"DEBUG: tweet text selector hit but empty: {selector}")

        print("DEBUG: selector-based extraction failed, trying article fallback")
        article_texts = page.eval_on_selector_all("article", "els => els.map(e => (e.innerText || '').trim())")
        print(f"DEBUG: article fallback count: {len(article_texts)}")
        fallback_text = _extract_text_from_article_fallback(article_texts)
        if fallback_text:
            print(f"DEBUG: article fallback selected: {_truncate_text(fallback_text, 120)}")
            return fallback_text

        print("DEBUG: tweet text could not be extracted from status page")
        return None


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(last_id: str) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_id": last_id}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def send_discord(
    webhook_url: str,
    status_url: str,
    post_text: Optional[str],
    username: str,
    text_failed: bool,
) -> None:
    if post_text:
        message = f"新着ポストを検知したよ\n@{TARGET_USERNAME}\n{post_text}\n{status_url}"
    elif text_failed:
        message = f"新着ポストを検知したよ\n@{TARGET_USERNAME}\n本文取得失敗\n{status_url}"
    else:
        message = f"新着ポストを検知したよ\n@{TARGET_USERNAME}\n{status_url}"

    payload = {
        "username": username,
        "content": _truncate_for_discord(message),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"Discord通知に失敗しました: status={response.status}")


def try_fetch_post_text(status_url: str) -> Tuple[Optional[str], bool]:
    try:
        post_text = fetch_post_text(status_url)
        if not post_text:
            print("WARN: 本文取得失敗のため URL のみで継続します")
            return None, True
        return post_text, False
    except (PlaywrightTimeoutError, PlaywrightError) as e:
        print(f"WARN: 個別ポストページ取得/抽出に失敗しました: {e}")
        print("WARN: 本文取得失敗のため URL のみで継続します")
        return None, True
    except Exception as e:
        print(f"WARN: 本文取得中に想定外エラー: {e}")
        print("WARN: 本文取得失敗のため URL のみで継続します")
        return None, True


def main() -> int:
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    discord_username = os.getenv("DISCORD_USERNAME", DEFAULT_DISCORD_USERNAME)

    if not webhook_url:
        print("ERROR: DISCORD_WEBHOOK_URL が未設定です", file=sys.stderr)
        return 1

    try:
        latest_status_url, page_title, current_url, hit_count = fetch_latest_status_url(TARGET_USERNAME)
        print(f"DEBUG: page title: {page_title}")
        print(f"DEBUG: page url: {current_url}")
        print(f"DEBUG: status link candidates: {hit_count}")

        state = load_state()
        last_id = state.get("last_id")

        # 初回実行: URL保存。本文取得は試すが失敗しても成功終了
        if not last_id:
            post_text, text_failed = try_fetch_post_text(latest_status_url)
            if post_text:
                print(f"INFO: 初回実行。最新本文ログ: {_truncate_text(post_text, LOG_TEXT_LIMIT)}")
            elif text_failed:
                print("INFO: 初回実行。本文取得失敗")
            save_state(latest_status_url)
            print("初回実行: 通知せず、last_id を保存しました")
            return 0

        # 2回目以降・新着なし: 本文だけ取得してログに出す（通知しない）
        if last_id == latest_status_url:
            post_text, text_failed = try_fetch_post_text(latest_status_url)
            if post_text:
                print(f"INFO: 新着なし。最新本文ログ: {_truncate_text(post_text, LOG_TEXT_LIMIT)}")
            elif text_failed:
                print("INFO: 新着なし。本文取得失敗")
            else:
                print("INFO: 新着なし。本文なし")
            return 0

        # 新着あり: 本文取得して通知（失敗時はURLのみで通知）
        post_text, text_failed = try_fetch_post_text(latest_status_url)
        send_discord(webhook_url, latest_status_url, post_text, discord_username, text_failed)
        save_state(latest_status_url)
        print("新着を通知して last_id を更新しました")
        return 0

    except (PlaywrightTimeoutError, PlaywrightError) as e:
        print(f"ERROR: Playwright実行に失敗しました: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
