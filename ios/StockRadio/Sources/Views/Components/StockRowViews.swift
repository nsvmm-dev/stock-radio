import SwiftUI

// ── お気に入り銘柄(ホーム用) ─────────────────────────────────────────

struct FavoriteStockRowView: View {
    let item: WatchlistItem

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(item.stockName)
                    .font(.headline)
                Text("\(item.stockCode) · \(item.market.marketDisplayName)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()
        }
        .padding(.vertical, 4)
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
                Text("\(item.stockCode) · \(item.market.marketDisplayName)")
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
