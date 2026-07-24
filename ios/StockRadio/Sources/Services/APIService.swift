import Foundation

// SAMデプロイ後に表示される ApiGatewayUrl に変更
private let baseURL = "https://69v9j095k7.execute-api.ap-northeast-1.amazonaws.com/Prod"

enum APIError: Error {
    case invalidURL
    case noData
    case decodingError
    case serverError(Int)
}

final class APIService {
    static let shared = APIService()
    private init() {}

    private func request<T: Decodable>(_ path: String, method: String = "GET",
                                        body: Encodable? = nil) async throws -> T {
        guard let url = URL(string: baseURL + path) else { throw APIError.invalidURL }

        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if let body {
            req.httpBody = try JSONEncoder().encode(body)
        }

        let (data, response) = try await URLSession.shared.data(for: req)

        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw APIError.serverError(http.statusCode)
        }

        return try JSONDecoder().decode(T.self, from: data)
    }

    // ── ユーザー ────────────────────────────────────────────────────

    func createUser(email: String, fcmToken: String) async throws -> UserResponse {
        struct Body: Encodable { let email: String; let fcmToken: String }
        return try await request("/users", method: "POST", body: Body(email: email, fcmToken: fcmToken))
    }

    func updateFCMToken(userId: String, token: String) async throws {
        struct Body: Encodable { let fcmToken: String }
        struct Empty: Decodable {}
        let _: Empty = try await request("/users/\(userId)/fcm-token", method: "PUT",
                                         body: Body(fcmToken: token))
    }

    // ── ラジオ ───────────────────────────────────────────────────────

    func listRadios(userId: String) async throws -> [RadioMeta] {
        struct Res: Decodable { let radios: [RadioMeta] }
        let res: Res = try await request("/users/\(userId)/radios")
        return res.radios
    }

    func getRadio(userId: String, date: String) async throws -> RadioDetail {
        return try await request("/users/\(userId)/radios/\(date)")
    }

    // ── ウォッチリスト ──────────────────────────────────────────────

    func getWatchlist(userId: String) async throws -> [WatchlistItem] {
        struct Res: Decodable { let watchlist: [WatchlistItem] }
        let res: Res = try await request("/users/\(userId)/watchlist")
        return res.watchlist
    }

    func addToWatchlist(userId: String, stockCode: String, stockName: String,
                        market: String) async throws -> WatchlistItem {
        struct Body: Encodable { let stockCode: String; let stockName: String; let market: String }
        return try await request("/users/\(userId)/watchlist", method: "POST",
                                  body: Body(stockCode: stockCode, stockName: stockName, market: market))
    }

    func removeFromWatchlist(userId: String, stockCode: String) async throws {
        struct Empty: Decodable {}
        let _: Empty = try await request("/users/\(userId)/watchlist/\(stockCode)", method: "DELETE")
    }

    // ── 株価ダッシュボード ──────────────────────────────────────────

    func getStockQuote(market: String, code: String) async throws -> StockQuote {
        return try await request("/stocks/\(market)/\(code)/quote")
    }

    func getHotStocks() async throws -> HotStocksResponse {
        return try await request("/stocks/hot")
    }

    func getStockNews(market: String, code: String, name: String) async throws -> [NewsItem] {
        struct Res: Decodable { let news: [NewsItem] }
        let encodedName = name.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
        let res: Res = try await request("/stocks/\(market)/\(code)/news?name=\(encodedName)")
        return res.news
    }
}
