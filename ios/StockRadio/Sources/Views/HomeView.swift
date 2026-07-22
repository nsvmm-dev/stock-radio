import SwiftUI

struct MainTabView: View {
    var body: some View {
        TabView {
            HomeView()
                .tabItem { Label("ホーム", systemImage: "radio") }
            SearchView()
                .tabItem { Label("検索", systemImage: "magnifyingglass") }
            MyPageView()
                .tabItem { Label("マイページ", systemImage: "person") }
        }
    }
}

// ── ホーム ────────────────────────────────────────────────────────

struct HomeView: View {
    @EnvironmentObject var appState: AppState
    @StateObject private var vm = HomeViewModel()

    var body: some View {
        NavigationStack {
            List {
                if vm.isLoading {
                    ProgressView("読み込み中...")
                        .frame(maxWidth: .infinity, alignment: .center)
                        .listRowSeparator(.hidden)
                } else if vm.radios.isEmpty {
                    ContentUnavailableView(
                        "ラジオがまだありません",
                        systemImage: "radio",
                        description: Text("毎朝7時に最新のラジオが届きます")
                    )
                } else {
                    ForEach(vm.radios) { radio in
                        NavigationLink(value: radio) {
                            RadioRowView(radio: radio)
                        }
                    }
                }
            }
            .listStyle(.plain)
            .navigationTitle("株価ラジオ")
            .navigationDestination(for: RadioMeta.self) { radio in
                RadioPlayerView(radio: radio)
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

struct RadioRowView: View {
    let radio: RadioMeta

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "waveform.circle.fill")
                .font(.largeTitle)
                .foregroundStyle(.blue)

            VStack(alignment: .leading, spacing: 4) {
                Text(radio.radioDate)
                    .font(.headline)
                Text(durationText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let count = radio.stockCount, count > 0 {
                    Text("\(count) 銘柄")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()
        }
        .padding(.vertical, 4)
    }

    private var durationText: String {
        guard let sec = radio.durationSec, sec > 0 else { return "..." }
        let min = sec / 60
        let s = sec % 60
        return String(format: "%d:%02d", min, s)
    }
}

// ── ViewModel ────────────────────────────────────────────────────

@MainActor
final class HomeViewModel: ObservableObject {
    @Published var radios: [RadioMeta] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    func load(userId: String) async {
        guard !userId.isEmpty else { return }
        isLoading = true
        defer { isLoading = false }

        do {
            radios = try await APIService.shared.listRadios(userId: userId)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
