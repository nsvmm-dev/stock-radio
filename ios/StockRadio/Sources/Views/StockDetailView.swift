import SwiftUI

struct StockDetailView: View {
    @Environment(\.appTheme) private var theme
    let ref: StockRef
    @StateObject private var vm: StockDetailViewModel
    @State private var selectedNews: NewsItem?

    init(ref: StockRef) {
        self.ref = ref
        _vm = StateObject(wrappedValue: StockDetailViewModel(ref: ref))
    }

    var body: some View {
        List {
            Section {
                Text("\(ref.code) · \(ref.market.marketDisplayName)")
                    .font(.caption)
                    .foregroundStyle(theme.secondaryText)
            }
            .listRowSeparator(.hidden)

            Section {
                if vm.isLoadingNews {
                    ProgressView()
                        .frame(maxWidth: .infinity, alignment: .center)
                } else if vm.news.isEmpty {
                    Text("関連ニュースが見つかりませんでした")
                        .font(.subheadline)
                        .foregroundStyle(theme.secondaryText)
                } else {
                    ForEach(vm.news) { item in
                        Button {
                            selectedNews = item
                        } label: {
                            NewsRowView(item: item)
                        }
                        .buttonStyle(.plain)
                    }
                }
            } header: {
                Text("ニュース")
                    .foregroundStyle(theme.secondaryText)
            }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .background(theme.background.ignoresSafeArea())
        .navigationTitle(ref.name)
        .navigationBarTitleDisplayMode(.inline)
        .sheet(item: $selectedNews) { news in
            if let url = URL(string: news.link) {
                SafariView(url: url)
            }
        }
        .task {
            await vm.load()
        }
    }
}

struct NewsRowView: View {
    @Environment(\.appTheme) private var theme
    let item: NewsItem

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(item.title)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(theme.primaryText)
                .lineLimit(2)
            HStack {
                Text(item.source)
                Spacer()
                Text(item.publishedAt.prefix(10))
            }
            .font(.caption)
            .foregroundStyle(theme.secondaryText)
        }
        .padding(.vertical, 2)
    }
}

// ── ViewModel ────────────────────────────────────────────────────

@MainActor
final class StockDetailViewModel: ObservableObject {
    let ref: StockRef
    @Published var news: [NewsItem] = []
    @Published var isLoadingNews = false

    init(ref: StockRef) {
        self.ref = ref
    }

    func load() async {
        isLoadingNews = true
        news = (try? await APIService.shared.getStockNews(market: ref.market, code: ref.code, name: ref.name)) ?? []
        isLoadingNews = false
    }
}
