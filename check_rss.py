#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.request
from typing import List, Tuple

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

STATE_FILE = "state.json"
DEFAULT_DISCORD_USERNAME = "X通知Bot"
TARGET_USERNAME = "F3yT8"


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


def fetch_latest_status_url(username: str) -> Tuple[str, str, str, int]:
    target_url = f"https://x.com/{username}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

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


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(last_id: str) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_id": last_id}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def send_discord(webhook_url: str, status_url: str, username: str) -> None:
    payload = {
        "username": username,
        "content": f"新着ポストを検知したよ\nタイトル: @{TARGET_USERNAME} の新着ポスト\nURL: {status_url}",
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

        if not last_id:
            save_state(latest_status_url)
            print("初回実行のため通知せず、last_id を保存しました")
            return 0

        if last_id == latest_status_url:
            print("新着なし")
            return 0

        send_discord(webhook_url, latest_status_url, discord_username)
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
