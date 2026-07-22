# iOSアプリ (Mac/Xcodeでビルド)

## Macでのセットアップ手順

### 1. Xcodeプロジェクトを作成

1. Xcode 15以上を起動
2. Create a new Xcode project → iOS → App
3. 設定:
   ```
   Product Name:     StockRadio
   Bundle Identifier: com.yourname.StockRadio  ← Firebaseに登録したものと同じ
   Interface:        SwiftUI
   Language:         Swift
   ```
4. 保存先: `ios/StockRadio/` フォルダの中に作成

### 2. Swiftソースファイルを追加

`Sources/` 以下のファイルをXcodeのプロジェクトナビゲータへドラッグ&ドロップ:
```
Sources/
  App/StockRadioApp.swift
  Models/Models.swift
  Services/APIService.swift
  Services/AudioPlayerService.swift
  Views/HomeView.swift
  Views/RadioPlayerView.swift
  Views/SearchView.swift
  Views/MyPageView.swift
```

### 3. APIエンドポイントを設定

`Sources/Services/APIService.swift` の `baseURL` を
SAMデプロイ後に取得した `ApiGatewayUrl` に変更:

```swift
private let baseURL = "https://XXXXXXXX.execute-api.ap-northeast-1.amazonaws.com/Prod"
```

### 4. Firebase SDKを追加

File → Add Package Dependencies:
- URL: `https://github.com/firebase/firebase-ios-sdk`
- バージョン: 最新
- 追加するモジュール:
  - `FirebaseCore`
  - `FirebaseMessaging`

### 5. GoogleService-Info.plistを追加

Firebaseコンソールからダウンロードした `GoogleService-Info.plist` を
Xcodeのプロジェクトルートにドラッグ&ドロップ。
「Copy items if needed」にチェック。

### 6. Capabilities設定

Project → Signing & Capabilities:
- `Background Modes` を追加:
  - ✅ Audio, AirPlay, and Picture in Picture
  - ✅ Background fetch
  - ✅ Remote notifications
- `Push Notifications` を追加

### 7. ビルド確認

Command + B でビルドエラーがないことを確認。

### 8. 実機テスト

USB接続したiPhoneを選択して Command + R で実行。

---

## ファイル構成

| ファイル | 役割 |
|---------|------|
| `StockRadioApp.swift` | エントリーポイント・Firebase初期化・APNs設定 |
| `Models.swift` | データモデル定義 |
| `APIService.swift` | バックエンドAPIとの通信 |
| `AudioPlayerService.swift` | AVPlayer・ロック画面コントロール |
| `HomeView.swift` | ラジオ一覧画面 |
| `RadioPlayerView.swift` | 再生画面（速度変更・スキップ対応）|
| `SearchView.swift` | ウォッチリスト管理画面 |
| `MyPageView.swift` | プラン変更・アカウント設定・オンボーディング |
