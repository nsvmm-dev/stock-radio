import SwiftUI

struct MyPageView: View {
    @EnvironmentObject var appState: AppState
    @StateObject private var vm = MyPageViewModel()
    @State private var selectedMarket = "US"
    @State private var pendingRadioLanguage: String?

    private let planOptions: [(String, String, String)] = [
        ("free",     localized("フリー"),       localized("1日間保存・広告あり")),
        ("standard", localized("スタンダード"), localized("1ヶ月保存・広告なし")),
        ("pro",      localized("プロ"),         localized("無制限保存・全機能")),
    ]

    private var filteredWatchlist: [WatchlistItem] {
        vm.watchlist.filter { $0.market == selectedMarket }
    }

    var body: some View {
        NavigationStack {
            List {
                Section("アカウント") {
                    LabeledContent("ユーザーID") {
                        Text(appState.userId ?? localized("未設定"))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    LabeledContent("現在のプラン") {
                        Text(Plan(rawValue: appState.plan)?.displayName ?? appState.plan)
                            .foregroundStyle(.blue)
                    }
                }

                Section("プランを変更") {
                    ForEach(planOptions, id: \.0) { value, name, desc in
                        PlanRow(
                            planValue: value,
                            planName: name,
                            description: desc,
                            isCurrentPlan: appState.plan == value
                        ) {
                            Task { await changePlan(to: value) }
                        }
                    }
                }

                Section("表示言語") {
                    Picker("表示言語", selection: $appState.displayLanguage) {
                        Text("日本語").tag("ja")
                        Text("English").tag("en")
                    }
                    .pickerStyle(.segmented)
                }

                Section {
                    if appState.plan == "free" {
                        LabeledContent("ラジオ言語") {
                            Text(appState.radioLanguage == "en" ? "English" : "日本語")
                                .foregroundStyle(.secondary)
                        }
                        Text("有料プランにアップグレードすると変更できます")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        Picker("ラジオ言語", selection: Binding(
                            get: { appState.radioLanguage },
                            set: { newValue in
                                if newValue != appState.radioLanguage {
                                    pendingRadioLanguage = newValue
                                }
                            }
                        )) {
                            Text("日本語").tag("ja")
                            Text("English").tag("en")
                        }
                        .pickerStyle(.segmented)
                        .disabled(vm.isChangingLanguage)

                        if vm.isChangingLanguage {
                            ProgressView()
                                .frame(maxWidth: .infinity, alignment: .center)
                        }

                        Text("変更は翌日の放送から反映されます。一度変更すると30日間は再変更できません。")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                } header: {
                    Text("ラジオ言語")
                }

                Section("お気に入り銘柄") {
                    Picker("市場", selection: $selectedMarket) {
                        Text("米国株").tag("US")
                        Text("日本株").tag("JP")
                    }
                    .pickerStyle(.segmented)

                    if vm.isLoading {
                        ProgressView()
                            .frame(maxWidth: .infinity, alignment: .center)
                    } else if filteredWatchlist.isEmpty {
                        Text("この市場のお気に入り銘柄はありません")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(filteredWatchlist) { item in
                            NavigationLink(value: StockRef(market: item.market, code: item.stockCode, name: item.stockName)) {
                                WatchlistRowView(item: item) {
                                    Task { await vm.remove(item, userId: appState.userId ?? "") }
                                }
                            }
                        }
                    }
                }

                Section("サポート") {
                    Link("利用規約", destination: URL(string: "https://example.com/terms")!)
                    Link("プライバシーポリシー", destination: URL(string: "https://example.com/privacy")!)
                }
            }
            .navigationTitle("マイページ")
            .navigationDestination(for: StockRef.self) { ref in
                StockDetailView(ref: ref)
            }
            .task {
                await vm.loadWatchlist(userId: appState.userId ?? "")
                await vm.refreshUser(appState: appState)
            }
            .confirmationDialog(
                "ラジオ言語を変更しますか？",
                isPresented: Binding(
                    get: { pendingRadioLanguage != nil },
                    set: { if !$0 { pendingRadioLanguage = nil } }
                ),
                titleVisibility: .visible
            ) {
                Button("変更する") {
                    if let language = pendingRadioLanguage {
                        Task { await vm.updateRadioLanguage(language, appState: appState) }
                    }
                    pendingRadioLanguage = nil
                }
                Button("キャンセル", role: .cancel) {
                    pendingRadioLanguage = nil
                }
            } message: {
                Text("変更は翌日の放送から反映されます。一度変更すると30日間は再変更できません。")
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

    private func changePlan(to plan: String) async {
        guard appState.userId != nil else { return }
        struct PlanBody: Encodable { let plan: String }
        // TODO: APIService に updatePlan を追加して呼び出す
        // 現状はローカル状態のみ更新
        appState.updatePlan(plan)
    }
}

@MainActor
final class MyPageViewModel: ObservableObject {
    @Published var watchlist: [WatchlistItem] = []
    @Published var isLoading = false
    @Published var isChangingLanguage = false
    @Published var errorMessage: String?

    func loadWatchlist(userId: String) async {
        guard !userId.isEmpty else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            watchlist = try await APIService.shared.getWatchlist(userId: userId)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// バックエンドの最新状態(プラン・ラジオ言語)でローカルのキャッシュを補正する
    func refreshUser(appState: AppState) async {
        guard let userId = appState.userId else { return }
        do {
            let user = try await APIService.shared.getUser(userId: userId)
            appState.updatePlan(user.plan)
            if let language = user.language {
                appState.updateRadioLanguage(language)
            }
        } catch {
            // オフライン等でも既存のローカルキャッシュ値で動作を継続する
        }
    }

    func updateRadioLanguage(_ language: String, appState: AppState) async {
        guard let userId = appState.userId else { return }
        isChangingLanguage = true
        defer { isChangingLanguage = false }
        do {
            let newLanguage = try await APIService.shared.updateRadioLanguage(userId: userId, language: language)
            appState.updateRadioLanguage(newLanguage)
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

struct PlanRow: View {
    let planValue: String
    let planName: String
    let description: String
    let isCurrentPlan: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(planName)
                        .font(.headline)
                        .foregroundStyle(.primary)
                    Text(description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if isCurrentPlan {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.blue)
                }
            }
        }
    }
}

// ── オンボーディング ────────────────────────────────────────────────

struct OnboardingView: View {
    @EnvironmentObject var appState: AppState
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            Image(systemName: "waveform.circle.fill")
                .font(.system(size: 80))
                .foregroundStyle(.blue.gradient)

            VStack(spacing: 8) {
                Text("株価ラジオ")
                    .font(.largeTitle.bold())
                Text("毎朝7時、あなたの銘柄の\n最新情報をラジオでお届け")
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            Spacer()

            Button {
                Task { await startApp() }
            } label: {
                Group {
                    if isLoading {
                        ProgressView()
                    } else {
                        Text("はじめる")
                            .font(.headline)
                    }
                }
                .frame(maxWidth: .infinity)
                .padding()
                .background(.blue)
                .foregroundStyle(.white)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .disabled(isLoading)
            .padding(.horizontal, 32)
            .padding(.bottom, 48)
        }
        .alert("エラー", isPresented: Binding(
            get: { errorMessage != nil },
            set: { if !$0 { errorMessage = nil } }
        )) {
            Button("OK") { errorMessage = nil }
        } message: {
            Text(errorMessage ?? "")
        }
    }

    private func startApp() async {
        isLoading = true
        defer { isLoading = false }

        do {
            let user = try await APIService.shared.createUser(
                email: "", fcmToken: "", language: appState.displayLanguage
            )
            appState.signIn(userId: user.userId, plan: user.plan,
                             radioLanguage: user.language ?? appState.displayLanguage)
        } catch {
            errorMessage = localized("サーバーに接続できません: \(error.localizedDescription)")
        }
    }
}
