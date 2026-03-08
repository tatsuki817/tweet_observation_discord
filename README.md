# X 1アカウント監視 → Discord通知（GitHub Actions最小構成）

このリポジトリは、**@F3yT8 のプロフィールページ（`https://x.com/F3yT8`）を Playwright で未ログイン閲覧し、最新投稿の本文とURLをDiscord Webhookへ通知する最小構成**です。  
有料Botサービスは使わず、GitHub Actionsの定期実行で動かします。

## 構成ファイル

- `check_rss.py`: Playwright でXプロフィールを開き、最新 `status` URL を抽出してDiscordへ通知
- `.github/workflows/rss_to_discord.yml`: 10分ごとの定期実行 + 手動実行
- `state.json`: 最後に処理した投稿URL（`last_id`）を保存

## 前提（public repository）

- public repository で GitHub Actions を使う前提
- 監視対象は **@F3yT8 のみ**
- GitHub Actions上で Playwright（Chromium）をインストールして実行

## GitHub Secrets の設定

リポジトリの **Settings > Secrets and variables > Actions > New repository secret** から、以下を設定してください。

- `DISCORD_WEBHOOK_URL`（必須）
- `DISCORD_USERNAME`（任意）
  - 未設定時は `X通知Bot` が使われます

## Discord Webhook URL の用意方法

1. Discordサーバーで通知先チャンネルを開く
2. **チャンネル編集 > 連携サービス > ウェブフック** を開く
3. 新しいWebhookを作成し、URLをコピー
4. そのURLを `DISCORD_WEBHOOK_URL` として Secrets に登録

## 動作仕様

1. Playwright で `https://x.com/F3yT8` を開く（未ログイン）
2. 少し待機してDOM描画後に `/F3yT8/status/<id>` を1件抽出
3. 新着を検知した場合、その個別ポストページを開いて本文を取得
4. `state.json` の `last_id` と比較
5. 初回実行（`last_id` が未保存）:
   - 最新URLと本文を取得
   - **初回テスト通知**を Discord に送信
   - `state.json` に最新URLを保存
6. 2回目以降（新着なし）:
   - 最新URLと本文を取得
   - Discord には通知しない
   - Actionsログに本文を出力（長文は一部省略）
7. 2回目以降（新着あり）:
   - 新しい投稿があれば本文付きで Discord Webhook へ通知
   - 通知後に `state.json` を更新

通知メッセージには以下を含みます。

- 初回: `初回テスト通知` + `@F3yT8` + `本文`（取得できた場合） + `URL`
- 通常新着: `新着ポストを検知` + `@F3yT8` + `本文`（取得できた場合） + `URL`
- 本文取得失敗時: `本文取得失敗` を含むフォールバック通知

## GitHub Actions 実行タイミング

- 定期実行: 10分ごと
- 手動実行: `workflow_dispatch`

ワークフローは `state.json` の変更があれば自動で commit/push します。

## 取得失敗時のログ

抽出失敗時は、Actionsログに以下を出力します。

- ページタイトル
- ページURL
- statusリンク候補件数
- 本文抽出に使ったselectorのヒット状況

## トラブル時の確認ポイント

- `DISCORD_WEBHOOK_URL` が正しいか
- Secrets 名が完全一致しているか（`DISCORD_WEBHOOK_URL`）
- Actions ログに `ERROR: Playwright実行に失敗しました` や `statusリンクを抽出できませんでした` が出ていないか
- 本文取得に失敗しても `本文取得失敗` のフォールバック通知が送られているか
- 新着なし時は Discord に通知せず、本文ログのみ出ているか
- X側の表示仕様変更やアクセス制限がないか

