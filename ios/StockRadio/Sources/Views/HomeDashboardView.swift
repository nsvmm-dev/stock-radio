import SwiftUI

struct HomeDashboardView: View {
    @EnvironmentObject var appState: AppState
    @StateObject private var vm = HomeDashboardViewModel()

    var body: some View {
        NavigationStack {
            List {
                Section {
                    if let today = vm.todaysRadio {
                        NavigationLink {
                            RadioPlayerView(radio: today)
                        } label: {
                            TodaysRadioRow(radio: today)
                        }
                    } else if vm.isLoadingRadios {
                        ProgressView()
                            .frame(maxWidth: .infinity, alignment: .center)
                    } else {
                        Text("今日のラジオはまだ届いていません")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                } header: {
                    HStack {
                        Text("今日のラジオ")
                        Spacer()
                        NavigationLink("すべて見る") {
                            RadioHistoryListView()
                        }
                        .font(.caption)
                        .textCase(nil)
                    }
                }

                Section("お気に入り銘柄") {
                    if vm.isLoadingWatchlist {
                        ProgressView()
                            .frame(maxWidth: .infinity, alignment: .center)
                    } else if vm.watchlist.isEmpty {
                        ContentUnavailableView(
                            "お気に入り銘柄がありません",
                            systemImage: "star",
                            description: Text("「検索」タブから銘柄を追加できます")
                        )
                    } else {
                        ForEach(vm.watchlist) { item in
                            NavigationLink(value: StockRef(market: item.market, code: item.stockCode, name: item.stockName)) {
                                FavoriteStockRowView(item: item, quote: vm.quotes[item.stockCode])
                            }
                        }
                    }
                }
            }
            .listStyle(.plain)
            .navigationTitle("株価ラジオ")
            .navigationDestination(for: StockRef.self) { ref in
                StockDetailView(ref: ref)
            }
            .refreshable {
                await vm.load(userId: appState.userId ?? "")
            }
            .task {
                await vm.load(userId: appState.userId ?? "")
            }
        }
    }
}

struct TodaysRadioRow: View {
    let radio: RadioMeta

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "play.circle.fill")
                .font(.largeTitle)
                .foregroundStyle(.blue)

            VStack(alignment: .leading, spacing: 4) {
                Text("今日のラジオを聴く")
                    .font(.headline)
                Text(durationText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()
        }
        .padding(.vertical, 4)
    }

    private var durationText: String {
        guard let sec = radio.durationSec, sec > 0 else { return "..." }
        return String(format: "%d:%02d", sec / 60, sec % 60)
    }
}

// ── ViewModel ────────────────────────────────────────────────────

@MainActor
final class HomeDashboardViewModel: ObservableObject {
    @Published var todaysRadio: RadioMeta?
    @Published var watchlist: [WatchlistItem] = []
    @Published var quotes: [String: StockQuote] = [:]
    @Published var isLoadingRadios = false
    @Published var isLoadingWatchlist = false
    @Published var errorMessage: String?

    private static let jstDateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.timeZone = TimeZone(identifier: "Asia/Tokyo")
        return f
    }()

    func load(userId: String) async {
        guard !userId.isEmpty else { return }

        isLoadingRadios = true
        isLoadingWatchlist = true

        async let radiosResult: [RadioMeta]? = try? APIService.shared.listRadios(userId: userId)
        async let watchlistResult: [WatchlistItem]? = try? APIService.shared.getWatchlist(userId: userId)

        let radios = await radiosResult
        let todayString = Self.jstDateFormatter.string(from: Date())
        todaysRadio = radios?.first(where: { $0.radioDate == todayString })
        isLoadingRadios = false

        watchlist = await watchlistResult ?? []
        isLoadingWatchlist = false

        await loadQuotes()
    }

    private func loadQuotes() async {
        await withTaskGroup(of: (String, StockQuote?).self) { group in
            for item in watchlist {
                group.addTask {
                    let quote = try? await APIService.shared.getStockQuote(market: item.market, code: item.stockCode)
                    return (item.stockCode, quote)
                }
            }
            for await (code, quote) in group {
                if let quote {
                    quotes[code] = quote
                }
            }
        }
    }
}
