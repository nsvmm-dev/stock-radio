import Foundation

// ── API レスポンスモデル ────────────────────────────────────────────

struct UserResponse: Codable {
    let userId: String
    let plan: String
    var email: String?
    var createdAt: String?
}

struct RadioMeta: Codable, Identifiable {
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
