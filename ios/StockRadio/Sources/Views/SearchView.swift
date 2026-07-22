import SwiftUI

struct SearchView: View {
    @EnvironmentObject var appState: AppState
    @StateObject private var vm = SearchViewModel()

    var body: some View {
        NavigationStack {
            List {
                if !vm.watchlist.isEmpty {
                    Section("ウォッチリスト") {
                        ForEach(vm.watchlist) { item in
                            WatchlistRowView(item: item) {
                                Task { await vm.remove(item, userId: appState.userId ?? "") }
                            }
                        }
                        .onDelete { indexSet in
                            for i in indexSet {
                                let item = vm.watchlist[i]
                                Task { await vm.remove(item, userId: appState.userId ?? "") }
                            }
                        }
                    }
                }

                Section("銘柄を追加") {
                    AddStockRow { code, name, market in
                        Task { await vm.add(code: code, name: name, market: market,
                                           userId: appState.userId ?? "") }
                    }
                }
            }
            .navigationTitle("銘柄検索")
            .task {
                await vm.loadWatchlist(userId: appState.userId ?? "")
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
}

struct WatchlistRowView: View {
    let item: WatchlistItem
    let onRemove: () -> Void

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(item.stockName)
                    .font(.headline)
                Text("\(item.stockCode) · \(item.market == "JP" ? "東証" : "米国")")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button(role: .destructive) { onRemove() } label: {
                Image(systemName: "minus.circle.fill")
                    .foregroundStyle(.red)
            }
            .buttonStyle(.plain)
        }
    }
}

struct AddStockRow: View {
    let onAdd: (String, String, String) -> Void
    @State private var code = ""
    @State private var name = ""
    @State private var market = "JP"

    var body: some View {
        VStack(spacing: 8) {
            HStack {
                TextField("コード (例: 7203)", text: $code)
                    .textInputAutocapitalization(.characters)
                Picker("市場", selection: $market) {
                    Text("東証").tag("JP")
                    Text("米国").tag("US")
                }
                .pickerStyle(.segmented)
                .frame(width: 120)
            }
            TextField("銘柄名 (例: トヨタ自動車)", text: $name)

            Button("追加") {
                guard !code.isEmpty, !name.isEmpty else { return }
                onAdd(code.uppercased(), name, market)
                code = ""
                name = ""
            }
            .buttonStyle(.borderedProminent)
            .frame(maxWidth: .infinity)
        }
        .padding(.vertical, 4)
    }
}

@MainActor
final class SearchViewModel: ObservableObject {
    @Published var watchlist: [WatchlistItem] = []
    @Published var errorMessage: String?

    func loadWatchlist(userId: String) async {
        guard !userId.isEmpty else { return }
        do {
            watchlist = try await APIService.shared.getWatchlist(userId: userId)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func add(code: String, name: String, market: String, userId: String) async {
        do {
            let item = try await APIService.shared.addToWatchlist(
                userId: userId, stockCode: code, stockName: name, market: market
            )
            watchlist.append(item)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func remove(_ item: WatchlistItem, userId: String) async {
        do {
            try await APIService.shared.removeFromWatchlist(userId: userId, stockCode: item.stockCode)
            watchlist.removeAll { $0.id == item.id }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
