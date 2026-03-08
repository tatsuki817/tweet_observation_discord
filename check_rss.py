#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.error
import urllib.request

STATE_FILE = "state.json"
DEFAULT_DISCORD_USERNAME = "X通知Bot"
TARGET_USERNAME = "F3yT8"


def fetch_profile_html(username: str) -> str:
    # Xプロフィールページを取得（最小構成のため標準ライブラリで実装）
    profile_url = f"https://x.com/{username}"
    req = urllib.request.Request(
        profile_url,
        headers={"User-Agent": "Mozilla/5.0 (x-profile-to-discord-bot)"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_latest_status_url(html: str, username: str) -> str:
    # HTML中から /<username>/status/<id> を1件抽出する
    # 先頭一致を「最新」として扱う（最小構成）
    pattern = re.compile(rf"/{re.escape(username)}/status/(\d+)", re.IGNORECASE)
    match = pattern.search(html)
    if not match:
        raise ValueError(
            f"{username} の最新 status URL をHTMLから抽出できませんでした。"
            "ページ構造変更、アクセス制限、または一時的な取得失敗の可能性があります。"
        )

    status_id = match.group(1)
    return f"https://x.com/{username}/status/{status_id}"


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
        html = fetch_profile_html(TARGET_USERNAME)
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
