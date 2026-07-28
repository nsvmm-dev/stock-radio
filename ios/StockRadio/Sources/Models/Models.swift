import Foundation

// ── API レスポンスモデル ────────────────────────────────────────────

struct UserResponse: Codable {
    let userId: String
    let plan: String
    var email: String?
    var createdAt: String?
    var language: String?
}

struct RadioMeta: Codable, Identifiable, Hashable {
    var id: String { radioDate }
    let userId: String
    let radioDate: String
    let durationSec: Int?
    let stockCount: Int?
    let createdAt: String?
}

struct RadioDetail: Codable {
    let userId: String
    let radioDate: String
    let s3Key: String
    let audioUrl: String?
    let durationSec: Int?
    let scriptLength: Int?
    let createdAt: String?
}

struct WatchlistItem: Codable, Identifiable {
    var id: String { stockCode }
    let userId: String
    let stockCode: String
    let stockName: String
    let market: String  // "JP" or "US"
    let addedAt: String?
}

// ── 株価ダッシュボード ──────────────────────────────────────────────

/// タブをまたいで株価詳細画面へ遷移するための共通キー
struct StockRef: Codable, Identifiable, Hashable {
    let market: String  // "JP" or "US"
    let code: String
    let name: String
    var id: String { "\(market)#\(code)" }
}

struct StockSearchResult: Codable, Identifiable, Hashable {
    let market: String
    let code: String
    let name: String
    var id: String { "\(market)#\(code)" }
}

struct NewsItem: Codable, Identifiable, Hashable {
    let title: String
    let summary: String
    let link: String
    let publishedAt: String
    let source: String
    let category: String
    var id: String { link }

    enum CodingKeys: String, CodingKey {
        case title, summary, link, source, category
        case publishedAt = "published_at"
    }
}

// ── プラン ────────────────────────────────────────────────────────

enum Plan: String, CaseIterable {
    case free = "free"
    case standard = "standard"
    case pro = "pro"

    var displayName: String {
        switch self {
        case .free:     return localized("フリー")
        case .standard: return localized("スタンダード")
        case .pro:      return localized("プロ")
        }
    }

    var retentionText: String {
        switch self {
        case .free:     return localized("1日間保存")
        case .standard: return localized("1ヶ月間保存")
        case .pro:      return localized("無制限保存")
        }
    }

    /// ラジオのナレーター音声品質(free=標準、standard/pro=高品質を自動選択)
    var voiceQualityText: String {
        self == .free ? localized("標準音声") : localized("高品質音声(Neural)")
    }
}

// ── 表示補助 ────────────────────────────────────────────────────────

let displayLanguageDefaultsKey = "display_language"

/// マイページの「表示言語」設定に基づいてローカライズ文字列を解決する。
/// SwiftUI の `.environment(\.locale:)` はビュー階層内の `Text` にしか効かないため、
/// ViewModel やモデル層で明示的にローカライズする際はこの関数を使う。
/// `String(localized:locale:)` は Bundle.main の解決に依存し確実に言語を
/// 切り替えられないケースがあるため、該当言語の .lproj バンドルを明示的に指定する。
func localized(_ value: String.LocalizationValue) -> String {
    let language = UserDefaults.standard.string(forKey: displayLanguageDefaultsKey) ?? "ja"
    guard let path = Bundle.main.path(forResource: language, ofType: "lproj"),
          let bundle = Bundle(path: path) else {
        return String(localized: value)
    }
    return String(localized: value, bundle: bundle)
}

extension String {
    /// "JP"/"US" マーケットコードの表示名(ローカライズ済み)
    var marketDisplayName: String {
        self == "JP" ? localized("東証") : localized("米国")
    }
}

// ── ローカルユーザー設定 ────────────────────────────────────────────

struct LocalUser: Codable {
    let userId: String
    var plan: String
    var radioLanguage: String?

    static let storageKey = "local_user"

    static func load() -> LocalUser? {
        guard let data = UserDefaults.standard.data(forKey: storageKey),
              let user = try? JSONDecoder().decode(LocalUser.self, from: data)
        else { return nil }
        return user
    }

    func save() {
        if let data = try? JSONEncoder().encode(self) {
            UserDefaults.standard.set(data, forKey: LocalUser.storageKey)
        }
    }
}
