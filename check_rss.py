#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import List, Tuple

STATE_FILE = "state.json"
DEFAULT_DISCORD_USERNAME = "X通知Bot"
TARGET_USERNAME = "F3yT8"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def fetch_profile_html(username: str) -> Tuple[str, str, int]:
    # x.com / twitter.com の順で取得を試す
    profile_urls = [
        f"https://x.com/{username}",
        f"https://twitter.com/{username}",
    ]

    last_error = None
    for profile_url in profile_urls:
        print(f"DEBUG: Fetch URL: {profile_url}")
        req = urllib.request.Request(
            profile_url,
            headers={"User-Agent": BROWSER_UA},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                status = getattr(response, "status", response.getcode())
                html = response.read().decode("utf-8", errors="replace")
                print(f"DEBUG: HTTP status: {status}")
                return html, profile_url, int(status)
        except urllib.error.HTTPError as e:
            print(f"DEBUG: HTTP status: {e.code} (error)")
            last_error = e
        except urllib.error.URLError as e:
            print(f"DEBUG: URL error: {e}")
            last_error = e

    if last_error:
        raise last_error
    raise RuntimeError("プロフィールページの取得に失敗しました")


def _collect_status_urls(html: str, username: str) -> List[str]:
    # 複数パターンで status URL を抽出
    patterns = [
        rf"https?://(?:x|twitter)\.com/{re.escape(username)}/status/(\d+)",
        rf"/{re.escape(username)}/status/(\d+)",
        rf"%2F{re.escape(username)}%2Fstatus%2F(\d+)",
    ]

    hits: List[str] = []
    for idx, pattern in enumerate(patterns, start=1):
        regex = re.compile(pattern, re.IGNORECASE)
        matches = regex.findall(html)
        print(f"DEBUG: regex[{idx}] hit count: {len(matches)}")
        for status_id in matches:
            url = f"https://x.com/{username}/status/{status_id}"
            if url not in hits:
                hits.append(url)

    print(f"DEBUG: total unique hit count: {len(hits)}")
    return hits


def extract_latest_status_url(html: str, username: str) -> str:
    hits = _collect_status_urls(html, username)
    if not hits:
        html_preview = html[:1000].replace("\n", "\\n")
        raise ValueError(
            f"{username} の最新 status URL をHTMLから抽出できませんでした。"
            f" HTML先頭プレビュー: {html_preview}"
            " ヒット件数: 0"
        )

    return hits[0]


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
    # 既存のWebhook通知方式を踏襲し、最小メッセージで通知
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
        html, fetched_url, fetched_status = fetch_profile_html(TARGET_USERNAME)
        print(f"DEBUG: Fetched URL: {fetched_url}")
        print(f"DEBUG: Fetched status: {fetched_status}")
        html_preview = html[:1000].replace('\n', '\\n')
        print(f"DEBUG: HTML preview (first 1000 chars): {html_preview}")

        latest_status_url = extract_latest_status_url(html, TARGET_USERNAME)

        state = load_state()
        last_id = state.get("last_id")

        # 初回実行: 通知せず最新URLだけ保存
        if not last_id:
            save_state(latest_status_url)
            print("初回実行のため通知せず、last_id を保存しました")
            return 0

        # 差分なし: 何もしない
        if last_id == latest_status_url:
            print("新着なし")
            return 0

        # 差分あり: 通知してstate更新
        send_discord(webhook_url, latest_status_url, discord_username)
        save_state(latest_status_url)
        print("新着を通知して last_id を更新しました")
        return 0

    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"ERROR: ネットワーク関連の失敗: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: 想定外の例外: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
