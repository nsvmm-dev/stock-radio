import SwiftUI

struct DiscoverView: View {
    @EnvironmentObject var appState: AppState
    @StateObject private var vm = DiscoverViewModel()

    var body: some View {
        NavigationStack {
            List {
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
            .alert("エラー", isPresented: Binding(
                get: { vm.errorMessage != nil },
                set: { if !$0 { vm.errorMessage = nil } }
            )) {
                Button("OK") { vm.errorMessage = nil }
            } message: {
                Text(vm.errorMessage ?? "")
            }
            .alert("追加しました", isPresented: Binding(
                get: { vm.addedStockName != nil },
                set: { if !$0 { vm.addedStockName = nil } }
            )) {
                Button("OK") { vm.addedStockName = nil }
            } message: {
                Text("「\(vm.addedStockName ?? "")」をお気に入り銘柄に追加しました。マイページから確認できます。")
            }
        }
    }
}

struct AddStockRow: View {
    let onAdd: (String, String, String) -> Void

    @State private var query = ""
    @State private var market = "US"
    @State private var searchResults: [StockSearchResult] = []
    @State private var isSearching = false
    @State private var selectedResult: StockSearchResult?
    @State private var searchTask: Task<Void, Never>?

    private var queryPlaceholder: String {
        market == "JP"
            ? localized("コードまたは銘柄名 (例: 7203 / トヨタ)")
            : localized("コードまたは銘柄名 (例: AAPL / Apple)")
    }
    private var trimmedQuery: String { query.trimmingCharacters(in: .whitespacesAndNewlines) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                TextField(queryPlaceholder, text: $query)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .onChange(of: query) { _, newValue in
                        scheduleSearch(newValue)
                    }
                Picker("市場", selection: $market) {
                    Text("米国").tag("US")
                    Text("東証").tag("JP")
                }
                .pickerStyle(.segmented)
                .frame(width: 120)
                .onChange(of: market) { _, _ in
                    scheduleSearch(query)
                }
            }

            if isSearching {
                ProgressView()
                    .frame(maxWidth: .infinity, alignment: .center)
            } else if !trimmedQuery.isEmpty && searchResults.isEmpty {
                Text("該当する銘柄が見つかりません")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(searchResults) { result in
                    Button {
                        selectedResult = result
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(result.name)
                                    .font(.subheadline.weight(.medium))
                                    .foregroundStyle(.primary)
                                Text(result.code)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Image(systemName: "plus.circle")
                                .foregroundStyle(.blue)
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.vertical, 4)
        .confirmationDialog(
            selectedResult.map { localized("「\($0.name)」を登録しますか？") } ?? "",
            isPresented: Binding(
                get: { selectedResult != nil },
                set: { if !$0 { selectedResult = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button("登録") {
                if let result = selectedResult {
                    onAdd(result.code, result.name, result.market)
                    query = ""
                    searchResults = []
                }
                selectedResult = nil
            }
            Button("キャンセル", role: .cancel) {
                selectedResult = nil
            }
        }
    }

    private func scheduleSearch(_ text: String) {
        searchTask?.cancel()
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            searchResults = []
            isSearching = false
            return
        }

        isSearching = true
        searchTask = Task {
            try? await Task.sleep(nanoseconds: 400_000_000)
            guard !Task.isCancelled else { return }

            let results = (try? await APIService.shared.searchStocks(query: trimmed, market: market)) ?? []
            guard !Task.isCancelled else { return }
            searchResults = results
            isSearching = false
        }
    }
}

@MainActor
final class DiscoverViewModel: ObservableObject {
    @Published var errorMessage: String?
    @Published var addedStockName: String?

    func add(code: String, name: String, market: String, userId: String) async {
        guard !userId.isEmpty else {
            errorMessage = localized("ユーザー情報が見つかりません。アプリを再起動してください。")
            return
        }
        do {
            let item = try await APIService.shared.addToWatchlist(
                userId: userId, stockCode: code, stockName: name, market: market
            )
            addedStockName = item.stockName
        } catch {
            errorMessage = localized("追加に失敗しました: \(error.localizedDescription)")
        }
    }
}
