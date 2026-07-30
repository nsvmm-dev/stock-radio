import SwiftUI

// ── ラジオ履歴一覧(ホームの「すべて見る」から遷移) ──────────────────

struct RadioHistoryListView: View {
    @EnvironmentObject var appState: AppState
    @Environment(\.appTheme) private var theme
    @StateObject private var vm = HomeViewModel()

    var body: some View {
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
                .foregroundStyle(theme.primaryText, theme.secondaryText)
            } else {
                ForEach(vm.radios) { radio in
                    NavigationLink(value: radio) {
                        RadioRowView(radio: radio)
                    }
                }
            }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .background(theme.background.ignoresSafeArea())
        .navigationTitle("ラジオ履歴")
        .navigationBarTitleDisplayMode(.inline)
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

struct RadioRowView: View {
    @Environment(\.appTheme) private var theme
    let radio: RadioMeta

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "waveform.circle.fill")
                .font(.largeTitle)
                .foregroundStyle(theme.accent)

            VStack(alignment: .leading, spacing: 4) {
                Text(radio.radioDate)
                    .font(.headline)
                    .foregroundStyle(theme.primaryText)
                Text(durationText)
                    .font(.caption)
                    .foregroundStyle(theme.secondaryText)
                if let count = radio.stockCount, count > 0 {
                    Text("\(count) " + localized("銘柄"))
                        .font(.caption2)
                        .foregroundStyle(theme.secondaryText)
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
