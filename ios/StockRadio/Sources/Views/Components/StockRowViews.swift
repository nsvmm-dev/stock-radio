import SwiftUI
import Charts

// ── ミニチャート ────────────────────────────────────────────────────

struct SparklineView: View {
    let history: [StockPricePoint]
    var color: Color = .blue

    var body: some View {
        Chart(history) { point in
            LineMark(x: .value("Date", point.date), y: .value("Close", point.close))
                .foregroundStyle(color)
                .interpolationMethod(.catmullRom)
        }
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .chartLegend(.hidden)
        .frame(width: 60, height: 32)
    }
}

// ── お気に入り銘柄(ホーム用) ─────────────────────────────────────────

struct FavoriteStockRowView: View {
    let item: WatchlistItem
    let quote: StockQuote?

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(item.stockName)
                    .font(.headline)
                Text("\(item.stockCode) · \(item.market == "JP" ? "東証" : "米国")")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            if let quote {
                SparklineView(history: quote.history, color: quote.changePct >= 0 ? .green : .red)
                PriceChangeView(latestClose: quote.latestClose, changePct: quote.changePct)
            } else {
                ProgressView()
            }
        }
        .padding(.vertical, 4)
    }
}

// ── 注目銘柄(発見タブ用) ─────────────────────────────────────────────

struct HotStockRowView: View {
    let stock: HotStock

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(stock.name)
                    .font(.headline)
                Text("\(stock.code) · \(stock.market == "JP" ? "東証" : "米国")")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            if let close = stock.latestClose, let pct = stock.changePct {
                PriceChangeView(latestClose: close, changePct: pct)
            }
        }
        .padding(.vertical, 4)
    }
}

// ── 価格・騰落率の共通表示 ───────────────────────────────────────────

struct PriceChangeView: View {
    let latestClose: Double
    let changePct: Double

    var body: some View {
        VStack(alignment: .trailing, spacing: 2) {
            Text(latestClose, format: .number.precision(.fractionLength(1)))
                .font(.subheadline.monospacedDigit())
            Text("\(changePct >= 0 ? "+" : "")\(changePct, specifier: "%.2f")%")
                .font(.caption.monospacedDigit())
                .foregroundStyle(changePct >= 0 ? .green : .red)
        }
    }
}

// ── ウォッチリスト行(マイページ用、SearchViewから移設) ───────────────

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
