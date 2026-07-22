# 株価ラジオ (Stock Radio)

毎朝、ウォッチリストの銘柄データ＋ニュースをAIが台本化し、音声ラジオとして配信するiOSアプリ。

## アーキテクチャ

```
[EventBridge 5:30 AM JST]
        ↓
[Lambda: radio_generator]
  ├─ J-Quants API (日本株)
  ├─ Alpha Vantage (米国株)
  ├─ RSS フィード (ニュース)
  ├─ Gemini Flash → Claude Sonnet (台本生成)
  └─ AWS Polly (音声合成)
        ↓
[S3: 音声MP3保存]  +  [DynamoDB: メタ情報]
        ↓
[EventBridge 7:00 AM JST]
        ↓
[Lambda: notification] → Firebase FCM → iOS App
```

## フォルダ構成

```
Stock_radio/
├── backend/          # AWS Lambda + SAM テンプレート
│   ├── template.yaml
│   ├── samconfig.toml
│   ├── config/       # dev/prod 設定
│   └── lambda/
│       ├── radio_generator/   # メインのラジオ生成
│       ├── api_handler/       # REST API
│       ├── notification/      # プッシュ通知
│       └── cleanup/           # 古いファイル削除
├── ios/              # iOSアプリ (Mac/Xcodeでビルド)
└── docs/             # セットアップガイド・設計書
```

## 開発環境

| 作業 | 環境 |
|------|------|
| バックエンド開発・テスト | Windows (本リポジトリ) |
| iOSアプリ開発・ビルド | Mac + Xcode |
| AWSデプロイ | Windows (AWS SAM CLI) |

## クイックスタート

1. `docs/setup_guide.md` を読んでAWS・各APIの設定を完了
2. `backend/` で SAM デプロイ
3. Mac で `ios/StockRadio/` を Xcode で開いてビルド

## APIプロバイダー切替 (本番前)

環境変数 `LLM_PROVIDER` を変更するだけ:

```bash
# テスト (無料)
LLM_PROVIDER=gemini

# 本番 (高品質)
LLM_PROVIDER=claude   # または openai
```

TTS品質も環境変数で切替:
```bash
# テスト (無料枠: Mizuki/standard)
TTS_ENGINE=standard

# 本番 (高品質: Kazuha/neural)
TTS_ENGINE=neural
```
