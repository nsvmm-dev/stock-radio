import SwiftUI
import Charts

struct StockDetailView: View {
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
                quoteHeader
            }
            .listRowSeparator(.hidden)

            Section("ニュース") {
                if vm.isLoadingNews {
                    ProgressView()
                        .frame(maxWidth: .infinity, alignment: .center)
                } else if vm.news.isEmpty {
                    Text("関連ニュースが見つかりませんでした")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
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
            }
        }
        .listStyle(.plain)
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

    @ViewBuilder
    private var quoteHeader: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("\(ref.code) · \(ref.market == "JP" ? "東証" : "米国")")
                .font(.caption)
                .foregroundStyle(.secondary)

            if let quote = vm.quote {
                HStack(alignment: .firstTextBaseline) {
                    Text(quote.latestClose, format: .number.precision(.fractionLength(1)))
                        .font(.title.bold())
                    Text("\(quote.changePct >= 0 ? "+" : "")\(quote.changePct, specifier: "%.2f")%")
                        .font(.headline)
                        .foregroundStyle(quote.changePct >= 0 ? .green : .red)
                }

                if quote.history.count >= 2 {
                    Chart(quote.history) { point in
                        LineMark(x: .value("Date", point.date), y: .value("Close", point.close))
                            .foregroundStyle(quote.changePct >= 0 ? .green : .red)
                            .interpolationMethod(.catmullRom)
                    }
                    .frame(height: 200)
                }
            } else if vm.isLoadingQuote {
                ProgressView()
                    .frame(maxWidth: .infinity, alignment: .center)
                    .frame(height: 200)
            } else {
                Text("株価データがまだありません")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .frame(height: 100)
            }
        }
        .padding(.vertical, 4)
    }
}

struct NewsRowView: View {
    let item: NewsItem

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(item.title)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.primary)
                .lineLimit(2)
            HStack {
                Text(item.source)
                Spacer()
                Text(item.publishedAt.prefix(10))
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
    }
}

// ── ViewModel ────────────────────────────────────────────────────

@MainActor
final class StockDetailViewModel: ObservableObject {
    let ref: StockRef
    @Published var quote: StockQuote?
    @Published var news: [NewsItem] = []
    @Published var isLoadingQuote = false
    @Published var isLoadingNews = false

    init(ref: StockRef) {
        self.ref = ref
    }

    func load() async {
        isLoadingQuote = true
        isLoadingNews = true

        async let quoteResult: StockQuote? = try? APIService.shared.getStockQuote(market: ref.market, code: ref.code)
        async let newsResult: [NewsItem]? = try? APIService.shared.getStockNews(market: ref.market, code: ref.code, name: ref.name)

        quote = await quoteResult
        isLoadingQuote = false

        news = await newsResult ?? []
        isLoadingNews = false
    }
}
