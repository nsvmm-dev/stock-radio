import Foundation

// SAMデプロイ後に表示される ApiGatewayUrl に変更
private let baseURL = "https://69v9j095k7.execute-api.ap-northeast-1.amazonaws.com/Prod"

enum APIError: Error {
    case invalidURL
    case noData
    case decodingError
    case serverError(Int)
}

struct APIMessageError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
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

    func createUser(email: String, fcmToken: String, language: String) async throws -> UserResponse {
        struct Body: Encodable { let email: String; let fcmToken: String; let language: String }
        return try await request("/users", method: "POST",
                                  body: Body(email: email, fcmToken: fcmToken, language: language))
    }

    func getUser(userId: String) async throws -> UserResponse {
        return try await request("/users/\(userId)")
    }

    func updateFCMToken(userId: String, token: String) async throws {
        struct Body: Encodable { let fcmToken: String }
        struct Empty: Decodable {}
        let _: Empty = try await request("/users/\(userId)/fcm-token", method: "PUT",
                                         body: Body(fcmToken: token))
    }

    /// ラジオ言語の変更。free プランやクールダウン中は 403 とともにサーバー側の
    /// メッセージ(次回変更可能日など)が返るため、専用のエラー型で伝える。
    func updateRadioLanguage(userId: String, language: String) async throws -> String {
        guard let url = URL(string: baseURL + "/users/\(userId)/language") else { throw APIError.invalidURL }

        var req = URLRequest(url: url)
        req.httpMethod = "PUT"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        struct Body: Encodable { let language: String }
        req.httpBody = try JSONEncoder().encode(Body(language: language))

        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse else { throw APIError.noData }

        if (200..<300).contains(http.statusCode) {
            struct Res: Decodable { let language: String }
            let res = try JSONDecoder().decode(Res.self, from: data)
            return res.language
        }

        struct ErrorRes: Decodable { let message: String?; let nextAvailableDate: String? }
        if let errRes = try? JSONDecoder().decode(ErrorRes.self, from: data) {
            var message = errRes.message ?? "ラジオ言語の変更に失敗しました"
            if let date = errRes.nextAvailableDate {
                message += "\n次回変更可能日: \(date)"
            }
            throw APIMessageError(message: message)
        }
        throw APIError.serverError(http.statusCode)
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

    func searchStocks(query: String, market: String) async throws -> [StockSearchResult] {
        struct Res: Decodable { let results: [StockSearchResult] }
        let encodedQuery = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
        let res: Res = try await request("/stocks/search?q=\(encodedQuery)&market=\(market)")
        return res.results
    }
}
