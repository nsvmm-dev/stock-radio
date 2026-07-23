# 株価ラジオ プロジェクト - Claude への引継ぎメモ

## プロジェクト概要
毎朝5:30 JSTに株価・ニュースからラジオ音声(MP3)を自動生成するiOSアプリ。
Windows で開発・AWSデプロイ、Mac で Xcode ビルド・App Store 申請。

## 現在の状況（2026-07-21時点）
- AWSバックエンド: デプロイ済み（ap-northeast-1, スタック名: stock-radio-dev）
- iOS Swiftコード: 作成済み（ios/StockRadio/Sources/）
- GitHub: https://github.com/nsvmm-dev/stock-radio.git
- Xcodeプロジェクト: **未作成**（Mac側でこれから作成する）

## 技術スタック
- バックエンド: AWS Lambda (Python 3.11) + SAM
- LLM: Groq (llama-3.3-70b-versatile) ← 無料。本番はClaude Sonnetに切替
- TTS: AWS Polly (Mizuki/standard) ← 無料。本番はKazuha/neuralに切替
- 日本株: J-Quants V2 API (x-api-key ヘッダー認証)
- 米国株: Alpha Vantage (ETF経由: DIA/QQQ/SPY)
- ニュース: RSS (NHK, Yahoo Japan Business, Bloomberg, WSJ, NYT)
- iOS: SwiftUI + AVPlayer + Firebase Messaging

## Mac側でやること（優先順）
1. Xcodeプロジェクト作成（xcodegen で自動化推奨）
2. ios/StockRadio/Sources/Services/APIService.swift の baseURL を設定
3. Simulator でビルド・テスト

## APIService.swift の baseURL
現在: `https://YOUR_API_ID.execute-api.ap-northeast-1.amazonaws.com/Prod`
→ AWS コンソール / CloudFormation の stock-radio-dev スタック outputs から ApiGatewayUrl を確認して設定

## 重要ファイル
- docs/setup_guide.md: 全手順（Step 5 が Mac 作業）
- backend/template.yaml: AWS SAM インフラ定義
- backend/lambda/radio_generator/: ラジオ生成ロジック
- ios/StockRadio/Sources/: Swift ソースコード（全8ファイル）
- deployment/switch_to_prod.ps1: 本番切替スクリプト（Windows で実行）

## Lambda 環境変数（AWS コンソールで設定済みか確認）
- LLM_PROVIDER=groq
- GROQ_API_KEY=（設定済みか確認）
- JQUANTS_API_KEY=（設定済みか確認）
- ALPHA_VANTAGE_API_KEY=（設定済みか確認）

## xcodegen でプロジェクト自動生成する場合
ios/StockRadio/ に project.yml を作成して `xcodegen generate` を実行。
詳細は Claude Code on Mac に「xcodegen でプロジェクトを作成して」と依頼する。
