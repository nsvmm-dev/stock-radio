import Foundation

// ── API レスポンスモデル ────────────────────────────────────────────

struct UserResponse: Codable {
    let userId: String
    let plan: String
    var email: String?
    var createdAt: String?
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

struct StockPricePoint: Codable, Identifiable, Hashable {
    let date: String
    let close: Double
    var id: String { date }
}

struct StockQuote: Codable {
    let market: String
    let code: String
    let name: String
    let latestClose: Double
    let changePct: Double
    let updatedAt: String?
    let history: [StockPricePoint]
}

struct HotStock: Codable, Identifiable {
    let market: String
    let code: String
    let name: String
    let latestClose: Double?
    let changePct: Double?
    var id: String { "\(market)#\(code)" }
}

struct HotStocksResponse: Codable {
    let usGainers: [HotStock]
    let usLosers: [HotStock]
    let usMostActive: [HotStock]
    let jpPopular: [HotStock]
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
        case .free:     return "フリー"
        case .standard: return "スタンダード"
        case .pro:      return "プロ"
        }
    }

    var retentionText: String {
        switch self {
        case .free:     return "1日間保存"
        case .standard: return "1ヶ月間保存"
        case .pro:      return "無制限保存"
        }
    }
}

// ── ローカルユーザー設定 ────────────────────────────────────────────

struct LocalUser: Codable {
    let userId: String
    var plan: String

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
