# API選定ガイド

## 要件との対比・改善点

### 要件 vs. 採用案

| カテゴリ | 要件の案 | 採用案（テスト） | 採用案（本番） | 理由 |
|---------|---------|---------------|--------------|------|
| 日本株データ | Alpha Vantage | **J-Quants** | J-Quants有料 | 東証公式・無料・商用OK |
| 米国株データ | Alpha Vantage | Alpha Vantage無料 | Alpha Vantage Premium | 25req/日で十分 |
| ニュース | NewsAPI | **RSSフィード** | RSSフィード | 無料・商用OK・**NewsAPIより高速** |
| 台本生成LLM | OpenAI GPT | **Gemini 1.5 Flash** | Claude Sonnet / GPT-4o | 無料枠大・商用OK |
| 音声合成TTS | ElevenLabs | **AWS Polly** | AWS Polly Neural | AWS内完結・無料5M字/月 |
| プッシュ通知 | SNS or Firebase | **Firebase FCM** | Firebase FCM | iOSに強い・無料 |

---

## 各API詳細

### 日本株: J-Quants API

- **提供元**: 日本取引所グループ (JPX) 公式
- **無料プラン**: Light プラン
  - 前日までの日足データ
  - 銘柄マスタ
  - 財務情報（四半期遅延）
- **商用利用**: OK（利用規約要確認）
- **登録**: https://jpx-jquants.com/

**コード例**:
```python
# トークン取得
POST https://api.jquants.com/v1/token/auth_user
{ "mailaddress": "...", "password": "..." }
→ refreshToken

POST https://api.jquants.com/v1/token/auth_refresh?refreshtoken=...
→ idToken

# 日足データ取得
GET https://api.jquants.com/v1/prices/daily_quotes?code=7203&date=20240101
Authorization: Bearer {idToken}
```

---

### ニュース: RSSフィード (feedparser)

NewsAPI の代替。無料・商用OK・レート制限なし。

**使用するRSSフィード**:
```
# 日本経済ニュース
https://finance.yahoo.co.jp/rss/topics/marketWatch  (Yahoo!ファイナンス)
https://www3.nhk.or.jp/rss/news/cat4.xml            (NHK経済)
https://feeds.jp.reuters.com/jp/marketsNews          (ロイター日本)

# 米国市場ニュース
https://feeds.bloomberg.com/markets/news.rss        (Bloomberg Markets)
https://feeds.a.dj.com/rss/RSSMarketsMain.xml       (WSJ Markets)
https://feeds.reuters.com/reuters/businessNews       (Reuters Business)
```

**NewsAPIと比べた優位性**:
- 無料プランのNewsAPIは**商用利用不可**（有料プランが必要）
- RSSは**商用利用OK**（各メディアの規約確認推奨）
- API呼び出しよりRSSの方が**レスポンスが速い**
- レート制限なし

---

### 台本生成LLM: 切替可能な設計

環境変数 `LLM_PROVIDER` で切替:

| Provider | ENV値 | 無料枠 | 商用 | 品質 | 速度 |
|----------|-------|--------|------|------|------|
| Gemini 1.5 Flash | `gemini` | 1500req/日 | ○ | ★★★ | ★★★★★ |
| Claude Sonnet | `claude` | なし | ○ | ★★★★★ | ★★★★ |
| GPT-4o | `openai` | なし | ○ | ★★★★★ | ★★★★ |

**テスト**: `LLM_PROVIDER=gemini`
**本番**: `LLM_PROVIDER=claude` または `openai`

変更はAWS Lambda環境変数を更新するだけ。コード変更不要。

---

### 音声合成: AWS Polly

ElevenLabs の代替。

| | ElevenLabs | AWS Polly |
|--|------------|-----------|
| 無料枠 | 10,000字/月 | **5,000,000字/月 (12ヶ月)** |
| 商用利用 | 有料プランのみ | ○ |
| AWS統合 | なし（外部API） | **ネイティブ統合** |
| 日本語品質 | ★★★★★ | ★★★★ (Neural) |
| コスト | $5/月〜 | $4/100万字 (standard) |

**日本語ボイス**:
- テスト: `Mizuki` (standard) → 無料枠内
- 本番: `Kazuha` (neural) → 自然な話し方

---

### プッシュ通知: Firebase Cloud Messaging (FCM)

- **無料**: 送信数無制限で無料
- **iOS対応**: APNs (Apple Push Notification service) をラップ
- **商用利用**: OK
- **Lambda統合**: `firebase-admin` Python SDK で送信

---

## アーキテクチャ上の改善点

### 1. EventBridge によるスケジューリング

Lambda の cron は EventBridge (CloudWatch Events) で管理:
```
5:30 AM JST (20:30 UTC) → ラジオ生成
6:00 AM JST (21:00 UTC) → クリーンアップ
7:00 AM JST (22:00 UTC) → プッシュ通知送信
```

### 2. データ共有キャッシュ

複数ユーザーが同じ銘柄を持っている場合、株価APIを1回だけ呼び出してキャッシュ:
- 市場全体データ (日経平均, TOPIX, DOW, NASDAQ) → Lambda実行中メモリで共有
- ユーザー個別データ (ウォッチリスト銘柄) → 重複呼び出しを回避

### 3. DynamoDB TTL による自動削除

プランごとの保持期間を DynamoDB の TTL (Time To Live) で管理:
```
無料プラン  → ttl = 現在 + 2日 (余裕を持たせる)
スタンダード → ttl = 現在 + 31日
プロ       → ttl なし (無制限)
```

Cleanup Lambda は S3 ファイルの削除を担当 (DynamoDB TTLはDBのみ削除するため)。

### 4. 米国市場対応タイミング

```
日本株の情報:
  取引時間: 9:00〜15:30 JST
  前日データ確定: 15:30 JST
  
米国株の情報:
  取引時間: 9:30〜16:00 ET = 22:30 JST 〜 5:00 JST (翌日)
  前日データ確定: 5:00 AM JST
  
→ 5:30 AM JST にラジオ生成開始が最適
  (米国市場終了後 + 日本市場開場前の情報を収録)
```
