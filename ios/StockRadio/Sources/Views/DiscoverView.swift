import SwiftUI

struct DiscoverView: View {
    @EnvironmentObject var appState: AppState
    @StateObject private var vm = DiscoverViewModel()

    var body: some View {
        NavigationStack {
            List {
                hotStocksSection(title: "米国 値上がり", stocks: vm.hotStocks?.usGainers)
                hotStocksSection(title: "米国 値下がり", stocks: vm.hotStocks?.usLosers)
                hotStocksSection(title: "米国 出来高上位", stocks: vm.hotStocks?.usMostActive)
                hotStocksSection(title: "日本 人気銘柄", stocks: vm.hotStocks?.jpPopular)

                Section("銘柄を追加") {
                    AddStockRow { code, name, market in
                        Task { await vm.add(code: code, name: name, market: market,
                                           userId: appState.userId ?? "") }
                    }
                }
            }
            .navigationTitle("検索")
            .navigationDestination(for: StockRef.self) { ref in
                StockDetailView(ref: ref)
            }
            .refreshable {
                await vm.loadHotStocks()
            }
            .task {
                await vm.loadHotStocks()
            }
            .alert("エラー", isPresented: Binding(
                get: { vm.errorMessage != nil },
                set: { if !$0 { vm.errorMessage = nil } }
            )) {
                Button("OK") { vm.errorMessage = nil }
            } message: {
                Text(vm.errorMessage ?? "")
            }
        }
    }

    @ViewBuilder
    private func hotStocksSection(title: String, stocks: [HotStock]?) -> some View {
        if let stocks, !stocks.isEmpty {
            Section(title) {
                ForEach(stocks) { stock in
                    NavigationLink(value: StockRef(market: stock.market, code: stock.code, name: stock.name)) {
                        HotStockRowView(stock: stock)
                    }
                }
            }
        }
    }
}

struct AddStockRow: View {
    let onAdd: (String, String, String) -> Void
    @State private var code = ""
    @State private var name = ""
    @State private var market = "US"

    private var trimmedCode: String { code.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var trimmedName: String { name.trimmingCharacters(in: .whitespacesAndNewlines) }

    private var codePlaceholder: String { market == "JP" ? "コード (例: 7203)" : "コード (例: AAPL)" }
    private var namePlaceholder: String { market == "JP" ? "銘柄名 (例: トヨタ自動車)" : "銘柄名 (例: Apple)" }

    var body: some View {
        VStack(spacing: 8) {
            HStack {
                TextField(codePlaceholder, text: $code)
                    .textInputAutocapitalization(.characters)
                Picker("市場", selection: $market) {
                    Text("米国").tag("US")
                    Text("東証").tag("JP")
                }
                .pickerStyle(.segmented)
                .frame(width: 120)
            }
            TextField(namePlaceholder, text: $name)

            Button("追加") {
                onAdd(trimmedCode.uppercased(), trimmedName, market)
                code = ""
                name = ""
            }
            .buttonStyle(.borderedProminent)
            .frame(maxWidth: .infinity)
            .disabled(trimmedCode.isEmpty || trimmedName.isEmpty)
        }
        .padding(.vertical, 4)
    }
}

@MainActor
final class DiscoverViewModel: ObservableObject {
    @Published var hotStocks: HotStocksResponse?
    @Published var errorMessage: String?

    func loadHotStocks() async {
        do {
            hotStocks = try await APIService.shared.getHotStocks()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func add(code: String, name: String, market: String, userId: String) async {
        do {
            _ = try await APIService.shared.addToWatchlist(
                userId: userId, stockCode: code, stockName: name, market: market
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
