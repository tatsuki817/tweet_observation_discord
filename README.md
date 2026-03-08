# X 1アカウント監視 → Discord通知（GitHub Actions最小構成）

このリポジトリは、**1人のXアカウント更新をRSS経由で監視し、Discord Webhookへ通知する最小構成**です。  
有料Botサービスは使わず、GitHub Actionsの定期実行で動かします。

## 構成ファイル

- `check_rss.py`: RSS/Atomを取得し、差分を判定してDiscordへ通知
- `.github/workflows/rss_to_discord.yml`: 10分ごとの定期実行 + 手動実行
- `state.json`: 最後に処理した投稿ID（`last_id`）を保存

## 前提（public repository）

- public repository で GitHub Actions を使う前提
- Python標準ライブラリのみ（外部ライブラリなし）
- 監視対象は1アカウントのみ

## GitHub Secrets の設定

リポジトリの **Settings > Secrets and variables > Actions > New repository secret** から、以下を設定してください。

- `RSS_URL`（必須）
- `DISCORD_WEBHOOK_URL`（必須）
- `DISCORD_USERNAME`（任意）
  - 未設定時は `X通知Bot` が使われます

## Discord Webhook URL の用意方法

1. Discordサーバーで通知先チャンネルを開く
2. **チャンネル編集 > 連携サービス > ウェブフック** を開く
3. 新しいWebhookを作成し、URLをコピー
4. そのURLを `DISCORD_WEBHOOK_URL` として Secrets に登録

## RSS_URL の例

XのRSSは公式提供ではないため、RSS変換サービス等のURLを使います。

例:

- `https://rsshub.app/twitter/user/<screen_name>`
- `https://nitter.net/<screen_name>/rss`

> 取得元サービスの仕様変更・停止により、動作が不安定になる場合があります。

## 動作仕様

1. RSS/Atomから最新投稿（先頭の1件）を取得
2. `state.json` の `last_id` と比較
3. 初回実行（`last_id` が未保存）:
   - **通知しない**
   - 最新IDのみ `state.json` に保存
4. 2回目以降:
   - 新しい投稿があれば Discord Webhook へ通知
   - 通知後に `state.json` を更新
   - 差分がなければ何もしない

通知メッセージには以下を含みます。

- `新着ポストを検知したよ`
- `タイトル`
- `URL`

## GitHub Actions 実行タイミング

- 定期実行: 10分ごと
- 手動実行: `workflow_dispatch`

ワークフローは `state.json` の変更があれば自動で commit/push します。

## トラブル時の確認ポイント

- `RSS_URL` が有効なRSS/Atomを返しているか
- `DISCORD_WEBHOOK_URL` が正しいか
- Secrets 名が完全一致しているか（`RSS_URL` / `DISCORD_WEBHOOK_URL`）
- Actions ログで以下のメッセージを確認
  - `初回実行のため通知せず、last_id を保存しました`
  - `新着なし`
  - エラーメッセージ（XML解析失敗、ネットワーク失敗など）

