# セットアップガイド（あなたがやること一覧）

## 全体の流れ

```
Step 1: AWSアカウント設定
Step 2: 外部API登録 (4つ)
Step 3: Firebase設定
Step 4: SAMデプロイ (Windows)
Step 5: iOS開発 (Mac)
Step 6: App Store申請 (Mac)
```

---

## Step 1: AWSアカウント設定

### 1-1. AWSアカウント作成
1. https://aws.amazon.com/jp/ にアクセス
2. 「無料で始める」をクリック
3. メールアドレス・パスワード・クレジットカード情報を入力
4. SMS認証を完了

### 1-2. 請求アラートの設定（重要 - 予期しない課金を防ぐ）
1. AWS コンソール右上のアカウント名 → 「請求とコスト管理」
2. 「請求設定」→「請求アラートを受け取る」にチェック
3. CloudWatch → アラーム → 「請求アラーム」作成
   - しきい値: $10（月）
   - 通知先: あなたのメールアドレス

### 1-3. IAMユーザー作成（本番環境用）
1. AWS コンソール → IAM → ユーザー → 「ユーザーを作成」
2. ユーザー名: `stock-radio-deploy`
3. 「アクセスキーを作成」→「CLI」を選択
4. アクセスキーIDとシークレットキーをメモ（一度しか表示されない）

### 1-4. AWS CLI設定（Windows）
```bash
# AWS CLIインストール
# https://aws.amazon.com/cli/ からダウンロード

# 設定
aws configure
# AWS Access Key ID: (1-3でメモしたキー)
# AWS Secret Access Key: (1-3でメモしたシークレット)
# Default region: ap-northeast-1  ← 東京リージョン
# Default output format: json
```

### 1-5. AWS SAM CLI インストール（Windows）
```bash
# https://github.com/aws/aws-sam-cli/releases から
# AWS SAM CLI x86_64 MSI をダウンロードしてインストール

# 確認
sam --version
```

---

## Step 2: 外部API登録

### 2-1. J-Quants API（日本株データ）- 無料・商用OK

1. https://jpx-jquants.com/ にアクセス
2. 「無料でお試し」→ アカウント登録
3. プラン: **Light プラン**（無料、個人・法人OK）
4. ダッシュボードからメールアドレスとパスワードをメモ
   - このメールアドレスが `JQUANTS_EMAIL` 環境変数になります（Gmailアド）
   - パスワードが `JQUANTS_PASSWORD` 環境変数になります(らんたん)

> **注意**: J-QuantsのLight プランは東証の公式データを使用します。
> 商用利用はLight プラン利用規約を確認してください。

### 2-2. Alpha Vantage（米国株データ）- 無料枠あり・商用OK

1. https://www.alphavantage.co/ にアクセス
2. 「Get your free API key」をクリック
3. メールアドレスを入力してAPIキーを取得
4. APIキーをメモ → `ALPHA_VANTAGE_API_KEY` 環境変数

> **無料枠**: 25リクエスト/日、5リクエスト/分
> **テスト段階**: 監視銘柄が少なければ十分
> **本番**: Premium プラン ($50/月〜) に切替

### 2-3. Google Gemini API（台本生成LLM）- 無料・商用OK

1. https://aistudio.google.com/ にアクセス
2. Googleアカウントでログイン
3. 「Get API key」→「Create API key」
4. APIキーをメモ → `GEMINI_API_KEY` 環境変数

> **無料枠**: Gemini 1.5 Flash = 15RPM, 1500リクエスト/日
> **商用利用**: 無料枠でも商用OK
> **本番**: Claude Sonnet / GPT-4o に切替（`LLM_PROVIDER` 環境変数を変更するだけ）

### 2-4. 本番LLM（デプロイ前に切替）

本番環境では以下のいずれかを使用予定:
↓↓デプロイ前に実施する。
**選択肢A: Claude Sonnet（Anthropic）**
- https://console.anthropic.com/ でAPIキー取得
- 環境変数: `LLM_PROVIDER=claude`, `ANTHROPIC_API_KEY=...`

**選択肢B: GPT-4o（OpenAI）**
- https://platform.openai.com/ でAPIキー取得
- 環境変数: `LLM_PROVIDER=openai`, `OPENAI_API_KEY=...`

---

## Step 3: Firebase設定（プッシュ通知）

### 3-1. Firebaseプロジェクト作成
1. https://console.firebase.google.com/ にアクセス
2. 「プロジェクトを作成」→ プロジェクト名: `stock-radio`
3. Googleアナリティクスは任意

### 3-2. iOSアプリ登録
1. プロジェクト → 「アプリを追加」→ iOSアイコン
2. バンドルID: `com.yourname.StockRadio`（後でXcodeに合わせる）
3. `GoogleService-Info.plist` をダウンロード（Xcodeプロジェクトに追加）

### 3-3. APNs設定（iOS通知用）⚠️ リリース前に実施（今は不要）

> Simulatorでは通知は届かないため、App Store申請前にまとめて対応でOK。
> 3-4のサービスアカウントキーも同じタイミングで実施。

1. Apple Developer Program に登録 ($99/年)
   - https://developer.apple.com/
2. Certificates, Identifiers & Profiles → Keys → 「+」
3. 「Apple Push Notifications service (APNs)」にチェック
4. `.p8` ファイルをダウンロード（一度しかダウンロードできない）
5. Firebase Console → プロジェクト設定 → Cloud Messaging
6. 「APNs認証キー」に `.p8` ファイルをアップロード

### 3-4. サービスアカウントキー取得
1. Firebase Console → プロジェクト設定 → サービスアカウント
2. 「新しい秘密鍵の生成」→ JSONをダウンロード
3. このJSONを AWS SSM Parameter Store に保存（後のStep 4で実施）

---

## Step 4: SAMデプロイ（Windows PowerShell）

> **3-4（Firebaseサービスアカウントキー）はスキップ。** 通知機能はリリース前に後から追加。
> ラジオ生成・API・クリーンアップは全て正常動作します。

---

### 4-0. 事前準備チェック

PowerShellで以下を順番に実行して、全部バージョンが表示されればOK。

```powershell
# Python バージョン確認（3.11 以上であればOK）
py --version
# → Python 3.11.x や 3.12.x と表示されればOK

# pip が使えるか確認
py -m pip --version

# AWS CLI が入っているか確認
aws --version
# → aws-cli/2.x.x と表示されればOK

# SAM CLI が入っているか確認
sam --version
# → SAM CLI, version 1.x.x と表示されればOK

# AWS の認証が通っているか確認
aws sts get-caller-identity
# → アカウントIDとARNが表示されればOK（エラーが出たら1-4の aws configure を再実行）
```

#### Python が入っていない場合

1. [python.org/downloads](https://www.python.org/downloads/) から Python 3.11 以上をダウンロード
2. インストーラー起動時 **「Add Python to PATH」に必ずチェック**
3. PowerShell を再起動してから `py --version` を再確認

---

### 4-1. SAM ビルド

```powershell
# プロジェクトのbackendフォルダへ移動
cd c:\02_App\Stock_radio\backend

# 依存ライブラリをインストールしてビルド
sam build
```

**正常終了時の表示:**
```
Building codeuri: lambda/radio_generator/
Building codeuri: lambda/api_handler/
Building codeuri: lambda/notification/
Building codeuri: lambda/cleanup/

Build Succeeded

Built Artifacts  : .aws-sam/build
```

#### よくあるエラーと対処

| エラーメッセージ | 対処 |
|----------------|------|
| `Python was not found` | Python 3.12 をインストール、PATH を確認 |
| `pip: command not found` | `python -m pip --version` で試す |
| `Error: Template format error` | template.yaml のインデントを確認 |
| `No module named 'pkg_resources'` | `pip install setuptools` を実行 |

---

### 4-2. SAM デプロイ（初回）

```powershell
sam deploy --guided
```

対話形式で設定を入力します。**太字**が入力箇所です。

```powershell
sam deploy --config-env dev `
  --parameter-overrides `
    "GroqApiKey=ここにGroqのAPIキー" `
    "JQuantsApiKey=ここにJ-QuantsのAPIキー" `
    "AlphaVantageApiKey=ここにAlpha VantageのAPIキー"
```

**各APIキーの取得先:**
- Groq: [console.groq.com](https://console.groq.com) → API Keys → Create（無料）
- J-Quants: [jpx-jquants.com](https://jpx-jquants.com) ダッシュボード → APIキー（Lightプラン無料）
- Alpha Vantage: [alphavantage.co](https://www.alphavantage.co/) → Get Free API Key（無料）

デプロイには **3〜5分** かかります。以下が流れます：

```
Deploying with following values
===============================
Initiating deployment
...
CloudFormation events from stack operations (refresh every 5.0 seconds)
CREATE_IN_PROGRESS  AWS::S3::Bucket          AudioBucket
CREATE_IN_PROGRESS  AWS::DynamoDB::Table     UsersTable
...
CREATE_COMPLETE     AWS::CloudFormation::Stack  stock-radio-dev

Successfully created/updated stack - stock-radio-dev in ap-northeast-1
```

---

### 4-3. デプロイ結果をメモ

デプロイ完了後に **Outputs** セクションが表示されます：

```
CloudFormation outputs from deployed stack
-----------------------------------------
Key                 ApiGatewayUrl
Description         API エンドポイントURL (iOSアプリに設定)
Value               https://xxxxxxxxxx.execute-api.ap-northeast-1.amazonaws.com/Prod

Key                 AudioBucketName
Value               stock-radio-audio-dev-123456789012
```

この2つを `.env` ファイルにメモしておいてください：

```
# .env に追記
API_GATEWAY_URL=https://xxxxxxxxxx.execute-api.ap-northeast-1.amazonaws.com/Prod
AUDIO_BUCKET=stock-radio-audio-dev-123456789012
```

---

### 4-4. 動作確認（AWSコンソール）

#### API の疎通確認

PowerShell で以下を実行（URLは自分のものに変更）：

```powershell
# テストユーザーを作成してAPIが動くか確認
$url = "https://xxxxxxxxxx.execute-api.ap-northeast-1.amazonaws.com/Prod"

Invoke-RestMethod -Uri "$url/users" -Method POST `
  -ContentType "application/json" `
  -Body '{"email":"test@example.com"}'

# → {"userId": "xxxx-xxxx-xxxx", "plan": "free"} が返ればOK
```

#### Lambda の手動実行（ラジオ生成テスト）

1. AWSコンソール → Lambda → `stock-radio-generator-dev`
2. 「テスト」タブ → イベントテンプレート: `{}` のまま → 「テスト」ボタン
3. 実行ログに `ラジオ生成完了` が出ればOK
4. S3 → `stock-radio-audio-dev-...` バケットに `.mp3` ファイルが作られているか確認

---

### 4-5. 2回目以降のデプロイ

コードを変更してデプロイし直す場合：

```powershell
cd c:\02_App\Stock_radio\backend
sam build
sam deploy   # --guided なしでOK（samconfig.toml を自動読込）
```

---

## Step 5: iOS開発・テスト（Mac で実施）

> ここからは Mac に切り替えて作業します。
> AWS デプロイは Windows で済んでいるため、Mac では Xcode のみ使います。

---

### Mac で必要なもの（インストールリスト）

| ツール | 入手先 | 所要時間 |
|--------|--------|----------|
| **Xcode** | App Store → 「Xcode」 | ダウンロード約7GB、30〜60分 |
| Firebase SDK | Xcode 内 (Swift Package Manager) | 5分 |
| AWS CLI / SAM CLI | **不要** | − |
| Python | **不要** | − |
| Homebrew | **不要** | − |

---

### 5-0. プロジェクトを Mac に持っていく

**方法A: USB / 外付けSSD（シンプル）**
```
c:\02_App\Stock_radio\ フォルダをまるごとコピー
→ Mac の ~/Documents/Stock_radio/ に貼り付け
```

**方法B: GitHub 経由（推奨・.gitignore で秘密情報は除外済み）**
```powershell
# Windows 側で実行
cd c:\02_App\Stock_radio
git init
git add .
git commit -m "initial"
git remote add origin https://github.com/yourname/stock-radio.git
git push -u origin main
```
```bash
# Mac 側で実行
git clone https://github.com/yourname/stock-radio.git ~/Documents/Stock_radio
```

---

### 5-1. Xcode インストール

1. Mac の **App Store** を開く → 「Xcode」で検索 → インストール
   - 約 7GB、Wi-Fi 接続で 30〜60 分かかります
2. インストール後 Xcode を起動 → 追加コンポーネントのインストールが走る（10〜20 分）
3. 完了確認：
   ```bash
   xcode-select --version
   # → xcode-select version 2397 などと表示されればOK
   ```

---

### 5-2. Xcode プロジェクト作成

1. Xcode → 「Create New Project」
2. **iOS** → **App** → Next
3. 以下を入力：

   | 項目 | 入力値 |
   |------|--------|
   | Product Name | `StockRadio` |
   | Bundle Identifier | `com.yourname.stockradio`（後で Firebase に合わせる） |
   | Interface | `SwiftUI` |
   | Language | `Swift` |

4. 保存先: `~/Documents/Stock_radio/ios/StockRadio/` を選択

---

### 5-3. デフォルトファイルを削除してソースを追加

1. Xcode が自動生成した `ContentView.swift` を削除（ゴミ箱へ）
2. Xcode 左ファイルツリーで `StockRadio` フォルダを右クリック
3. 「Add Files to "StockRadio"...」
4. `~/Documents/Stock_radio/ios/StockRadio/Sources/` フォルダを選択
5. 「Added folders: **Create groups**」を選択 → Add

追加されるファイル：
```
Sources/
  App/StockRadioApp.swift       ← エントリポイント
  Models/Models.swift
  Services/APIService.swift
  Services/AudioPlayerService.swift
  Views/HomeView.swift
  Views/RadioPlayerView.swift
  Views/SearchView.swift
  Views/MyPageView.swift        ← OnboardingView も含む
```

---

### 5-4. API エンドポイントを設定

`Sources/Services/APIService.swift` の先頭を編集：

```swift
// 変更前
private let baseURL = "https://YOUR_API_ID.execute-api.ap-northeast-1.amazonaws.com/Prod"

// 変更後（Step 4-3 でコピーした ApiGatewayUrl）
private let baseURL = "https://xxxxxxxxxx.execute-api.ap-northeast-1.amazonaws.com/Prod"
```

---

### 5-5. Firebase SDK を追加

1. Xcode メニュー → **File** → **Add Package Dependencies**
2. 検索欄に貼り付け：
   ```
   https://github.com/firebase/firebase-ios-sdk
   ```
3. バージョン: 最新のまま → **Add Package**
4. 追加するモジュールを選択:
   - ✅ `FirebaseCore`
   - ✅ `FirebaseMessaging`
   - 他はチェック不要 → **Add Package**

> **注意**: `GoogleService-Info.plist` がなくてもビルドは通ります（プッシュ通知だけが無効）。
> Firebase セットアップ（Step 3-1）をしていない場合は 5-6 をスキップしてOK。

---

### 5-6. GoogleService-Info.plist を追加（Firebase 設定済みの場合のみ）

1. Firebase Console で取得した `GoogleService-Info.plist` を用意
2. Xcode のプロジェクトルートにドラッグ
3. ダイアログ: 「**Copy items if needed**」にチェック → Finish

---

### 5-7. Capabilities 設定

1. Xcode 左ツリーの一番上 `StockRadio`（青いアイコン）をクリック
2. **Signing & Capabilities** タブ
3. **Team**: Apple アカウントを選択（無料アカウントでもOK・Simulator実行なら不要）
4. 「**+ Capability**」をクリックして以下を追加：
   - `Background Modes` → 以下にチェック：
     - ✅ Audio, AirPlay, and Picture in Picture
     - ✅ Background fetch
     - ✅ Remote notifications
   - `Push Notifications`（リリース時に必要、今は追加だけしておく）

---

### 5-8. ビルドして Simulator で確認

1. 左上のデバイス選択 → **iPhone 16** などを選択
2. **⌘B** でビルド → エラーがないことを確認
3. **⌘R** で Simulator 起動

**確認ポイント（順番に試す）：**

| 確認 | 期待する結果 |
|------|------------|
| 「はじめる」をタップ | ユーザーIDが発行されてホーム画面に遷移 |
| ウォッチリスト → 銘柄を追加 | リストに追加される |
| Lambda を手動実行（AWS コンソール）後にリロード | ホームにラジオが表示される |
| ラジオをタップ | 音声が再生される |

---

## Step 6: 本番切替・App Store 申請（Mac で実施）

> Step 5 でテストが完了してからまとめて実施します。

---

### 6-1. 本番 API への切替（AWS コンソールで実施）

#### LLM を Gemini → Claude Sonnet に切替

1. AWSコンソール → Lambda → `stock-radio-generator-prod`
2. 「設定」→「環境変数」→「編集」
3. 以下を変更：

   | 環境変数 | 変更前 | 変更後 |
   |---------|--------|--------|
   | `LLM_PROVIDER` | `gemini` | `claude` |
   | `ANTHROPIC_API_KEY` | 空 | Anthropicのキー |
   | `TTS_ENGINE` | `standard` | `neural` |

4. 保存 → 次の実行から即反映

#### 本番デプロイ（Windows で実施）

```powershell
cd c:\02_App\Stock_radio\backend
sam build
sam deploy --config-env prod
```

---

### 6-2. Firebase 通知設定（⚠️ここで初めて 3-3・3-4 を実施）

1. **3-3 APNs設定** を実施（Apple Developer Program $99/年登録）
2. **3-4 サービスアカウントキー** を取得してSSMに保存：

```powershell
# Mac のターミナル or Windows PowerShell どちらでもOK
$cred = Get-Content "firebase-credentials.json" -Raw
aws ssm put-parameter `
  --name "/stock-radio/prod/firebase-credentials" `
  --value $cred `
  --type "SecureString" `
  --region ap-northeast-1
```

---

### 6-3. App Store Connect の設定（Mac で実施）

1. [appstoreconnect.apple.com](https://appstoreconnect.apple.com) にアクセス
2. 「マイ App」→「+」→「新規 App」
3. 以下を入力：

   | 項目 | 内容 |
   |------|------|
   | プラットフォーム | iOS |
   | 名前 | 株価ラジオ |
   | プライマリ言語 | 日本語 |
   | バンドル ID | Xcode と同じもの |
   | SKU | `stock-radio-ios-001` |

4. **スクリーンショット**: iPhone 6.7インチ サイズを Simulator で撮影（⌘+S）
5. **説明文**: アプリの概要を日本語で記載
6. **年齢制限**: 4+ でOK（金融情報のみ）
7. **カテゴリ**: Finance（ファイナンス）

---

### 6-4. Xcode から App Store にアップロード（Mac で実施）

1. Xcode → デバイス選択を「Any iOS Device」に変更
2. メニュー → **Product** → **Archive**（ビルドに5〜10分かかる）
3. Organizer ウィンドウが開く → 「**Distribute App**」
4. 「**App Store Connect**」→ Next → Upload → Next
5. アップロード完了後、App Store Connect で審査に提出

**審査期間**: 通常 1〜3 日

---

## 本番切替チェックリスト

```
□ AWS Claude / GPT-4o の API キー取得
□ LLM_PROVIDER=claude に変更（Lambda環境変数）
□ TTS_ENGINE=neural に変更（Lambda環境変数）
□ Alpha Vantage Premium プランに切替（$50/月〜）
□ 3-3 APNs設定（Apple Developer Program $99/年）
□ 3-4 Firebase サービスアカウントキーをSSMに保存
□ sam deploy --config-env prod で本番デプロイ
□ App Store Connect でアプリ情報入力
□ Xcode Archive → App Store にアップロード
□ 審査提出
```

---

## コスト見積もり（月間）

### テスト段階（ユーザー数: 1〜10人）
| サービス | コスト |
|---------|--------|
| AWS Lambda | 無料枠内 $0 |
| DynamoDB | 無料枠内 $0 |
| S3 | ほぼ $0 |
| AWS Polly (standard) | 無料枠 5M字/月 $0 |
| Gemini Flash | 無料 $0 |
| J-Quants Light | 無料 $0 |
| Alpha Vantage | 無料 $0 |
| **合計** | **ほぼ $0** |

### 本番（ユーザー数: 1000人）
| サービス | コスト目安 |
|---------|-----------|
| AWS Lambda | ~$5 |
| DynamoDB | ~$10 |
| S3 + CloudFront | ~$5 |
| AWS Polly Neural | ~$60 (1000ユーザー × 1500字/日) |
| Claude Sonnet | ~$30 |
| J-Quants (有料) | ~$3,000/月 ← **要検討** |
| **合計** | **~$3,100/月** |

> J-Quantsの有料プランは高額なため、ユーザー数が増えてから検討。
> 代替として、東証の無料データやyfinanceの併用も検討余地あり。
