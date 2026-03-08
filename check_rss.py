#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Optional, Tuple

STATE_FILE = "state.json"
DEFAULT_DISCORD_USERNAME = "X通知Bot"


def fetch_rss(url: str) -> str:
    # RSS/Atomを取得する（User-Agentを付けてブロックされにくくする）
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (rss-to-discord-bot)"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def _text(elem: Optional[ET.Element]) -> str:
    if elem is None or elem.text is None:
        return ""
    return elem.text.strip()


def parse_latest_post(feed_xml: str) -> Tuple[str, str, str]:
    # RSS 2.0 / Atom の両方に対応して最新エントリを1件取得する
    root = ET.fromstring(feed_xml)

    # RSS 2.0
    if root.tag.lower().endswith("rss"):
        channel = root.find("channel")
        if channel is None:
            raise ValueError("RSS channel が見つかりません")
        item = channel.find("item")
        if item is None:
            raise ValueError("RSS item が見つかりません")

        title = _text(item.find("title"))
        link = _text(item.find("link"))
        item_id = _text(item.find("guid")) or link or title
        if not item_id:
            raise ValueError("RSS item からIDを生成できません")
        return item_id, title or "(タイトルなし)", link

    # Atom
    if root.tag.lower().endswith("feed"):
        entry = None
        for child in root:
            if child.tag.lower().endswith("entry"):
                entry = child
                break
        if entry is None:
            raise ValueError("Atom entry が見つかりません")

        title = ""
        link = ""
        entry_id = ""

        for child in entry:
            tag = child.tag.lower()
            if tag.endswith("title"):
                title = _text(child)
            elif tag.endswith("id"):
                entry_id = _text(child)
            elif tag.endswith("link"):
                rel = child.attrib.get("rel", "alternate")
                href = child.attrib.get("href", "")
                if rel == "alternate" and href and not link:
                    link = href
                if href and not link:
                    link = href

        item_id = entry_id or link or title
        if not item_id:
            raise ValueError("Atom entry からIDを生成できません")
        return item_id, title or "(タイトルなし)", link

    raise ValueError("RSS 2.0 または Atom 形式ではありません")


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(last_id: str) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_id": last_id}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def send_discord(webhook_url: str, title: str, post_url: str, username: str) -> None:
    # Discord Webhookへ最小構成で通知する
    payload = {
        "username": username,
        "content": f"新着ポストを検知したよ\nタイトル: {title}\nURL: {post_url}",
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
    rss_url = os.getenv("RSS_URL")
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    username = os.getenv("DISCORD_USERNAME", DEFAULT_DISCORD_USERNAME)

    if not rss_url:
        print("ERROR: RSS_URL が未設定です", file=sys.stderr)
        return 1
    if not webhook_url:
        print("ERROR: DISCORD_WEBHOOK_URL が未設定です", file=sys.stderr)
        return 1

    try:
        feed_xml = fetch_rss(rss_url)
        latest_id, latest_title, latest_link = parse_latest_post(feed_xml)
        state = load_state()
        last_id = state.get("last_id")

        # 初回実行: 通知せず最新IDだけ保存
        if not last_id:
            save_state(latest_id)
            print("初回実行のため通知せず、last_id を保存しました")
            return 0

        # 差分なし: 何もしない
        if last_id == latest_id:
            print("新着なし")
            return 0

        # 差分あり: 通知してstate更新
        send_discord(webhook_url, latest_title, latest_link, username)
        save_state(latest_id)
        print("新着を通知して last_id を更新しました")
        return 0

    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"ERROR: ネットワーク関連の失敗: {e}", file=sys.stderr)
        return 1
    except ET.ParseError as e:
        print(f"ERROR: RSS/Atom のXML解析に失敗: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: 想定外の例外: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
