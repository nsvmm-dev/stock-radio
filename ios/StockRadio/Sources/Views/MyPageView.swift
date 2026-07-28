import SwiftUI
import StoreKit
import AuthenticationServices

struct MyPageView: View {
    @EnvironmentObject var appState: AppState
    @Environment(\.appTheme) private var theme
    @StateObject private var vm = MyPageViewModel()
    @StateObject private var purchaseService = PurchaseService()
    @State private var selectedMarket = "US"
    @State private var pendingRadioLanguage: String?

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
                            .foregroundStyle(theme.secondaryText)
                    }
                    LabeledContent("現在のプラン") {
                        Text(Plan(rawValue: appState.plan)?.displayName ?? appState.plan)
                            .foregroundStyle(theme.accent)
                    }
                }

                Section("外観") {
                    Picker("外観", selection: $appState.uiTheme) {
                        ForEach(AppTheme.allCases, id: \.self) { t in
                            Text(t.displayName).tag(t)
                        }
                    }
                    .pickerStyle(.segmented)
                }

                Section {
                    PlanRow(
                        planValue: "free",
                        planName: localized("フリー"),
                        description: localized("1日間保存・広告あり"),
                        isCurrentPlan: appState.plan == "free",
                        onSelect: nil
                    )

                    ForEach(purchaseService.products) { product in
                        PlanRow(
                            planValue: product.id,
                            planName: product.displayName,
                            description: "\(product.displayPrice) / \(localized("月"))",
                            isCurrentPlan: appState.plan == PurchaseService.planName(for: product.id)
                        ) {
                            Task { await purchase(product) }
                        }
                    }

                    if purchaseService.isLoading {
                        ProgressView()
                            .frame(maxWidth: .infinity, alignment: .center)
                    }

                    Button {
                        Task { await restore() }
                    } label: {
                        Text("購入を復元")
                    }
                } header: {
                    Text("プランを変更")
                } footer: {
                    Text("フリーへの変更(解約)はiPhoneの設定 > Apple ID > サブスクリプション から行えます")
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
                                .foregroundStyle(theme.secondaryText)
                        }
                        Text("有料プランにアップグレードすると変更できます")
                            .font(.caption)
                            .foregroundStyle(theme.secondaryText)
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
                            .foregroundStyle(theme.secondaryText)
                    }
                } header: {
                    Text("ラジオ言語")
                }

                Section {
                    LabeledContent("ラジオ音声") {
                        Text(Plan(rawValue: appState.plan)?.voiceQualityText ?? "")
                            .foregroundStyle(theme.secondaryText)
                    }
                    if appState.plan == "free" {
                        Text("有料プランでは高品質な音声(Neural)が自動的に使われます")
                            .font(.caption)
                            .foregroundStyle(theme.secondaryText)
                    }
                } header: {
                    Text("ラジオ音声")
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
                            .foregroundStyle(theme.secondaryText)
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
            .scrollContentBackground(.hidden)
            .background(theme.background.ignoresSafeArea())
            .navigationTitle("マイページ")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: StockRef.self) { ref in
                StockDetailView(ref: ref)
            }
            .task {
                await vm.loadWatchlist(userId: appState.userId ?? "")
                await vm.refreshUser(appState: appState)

                purchaseService.userId = appState.userId
                await purchaseService.loadProducts()
                if let userId = appState.userId,
                   let plan = await purchaseService.syncCurrentEntitlement(userId: userId) {
                    appState.updatePlan(plan)
                }
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
            .alert("エラー", isPresented: Binding(
                get: { purchaseService.errorMessage != nil },
                set: { if !$0 { purchaseService.errorMessage = nil } }
            )) {
                Button("OK") { purchaseService.errorMessage = nil }
            } message: {
                Text(purchaseService.errorMessage ?? "")
            }
        }
    }

    private func purchase(_ product: Product) async {
        guard let userId = appState.userId else { return }
        if let plan = await purchaseService.purchase(product, userId: userId) {
            appState.updatePlan(plan)
        }
    }

    private func restore() async {
        guard let userId = appState.userId else { return }
        if let plan = await purchaseService.restorePurchases(userId: userId) {
            appState.updatePlan(plan)
        }
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
    @Environment(\.appTheme) private var theme
    let planValue: String
    let planName: String
    let description: String
    let isCurrentPlan: Bool
    var onSelect: (() -> Void)?

    var body: some View {
        Group {
            if let onSelect {
                Button(action: onSelect) { rowContent }
            } else {
                rowContent
            }
        }
    }

    private var rowContent: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(planName)
                    .font(.headline)
                    .foregroundStyle(theme.primaryText)
                Text(description)
                    .font(.caption)
                    .foregroundStyle(theme.secondaryText)
            }
            Spacer()
            if isCurrentPlan {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(theme.accent)
            }
        }
    }
}

// ── オンボーディング ────────────────────────────────────────────────

struct OnboardingView: View {
    @EnvironmentObject var appState: AppState
    @Environment(\.appTheme) private var theme
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
                    .foregroundStyle(theme.secondaryText)
                    .multilineTextAlignment(.center)
            }

            Spacer()

            SignInWithAppleButton(.signIn) { request in
                request.requestedScopes = [.fullName, .email]
            } onCompletion: { result in
                Task { await handle(result: result) }
            }
            .signInWithAppleButtonStyle(.black)
            .frame(height: 50)
            .padding(.horizontal, 32)
            .padding(.bottom, 48)
            .disabled(isLoading)
            .overlay {
                if isLoading {
                    ProgressView()
                }
            }
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

    private func handle(result: Result<ASAuthorization, Error>) async {
        switch result {
        case .success(let authorization):
            guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
                  let tokenData = credential.identityToken,
                  let identityToken = String(data: tokenData, encoding: .utf8) else {
                errorMessage = localized("サインインに失敗しました")
                return
            }
            await signIn(identityToken: identityToken, email: credential.email)
        case .failure(let error):
            if (error as? ASAuthorizationError)?.code != .canceled {
                errorMessage = localized("サインインに失敗しました: \(error.localizedDescription)")
            }
        }
    }

    private func signIn(identityToken: String, email: String?) async {
        isLoading = true
        defer { isLoading = false }

        do {
            let user = try await APIService.shared.signInWithApple(
                identityToken: identityToken, email: email, language: appState.displayLanguage
            )
            appState.signIn(userId: user.userId, plan: user.plan,
                             radioLanguage: user.language ?? appState.displayLanguage)
        } catch {
            errorMessage = localized("サーバーに接続できません: \(error.localizedDescription)")
        }
    }
}
