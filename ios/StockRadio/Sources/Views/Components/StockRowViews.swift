import SwiftUI

// ── お気に入り銘柄(ホーム用) ─────────────────────────────────────────

struct FavoriteStockRowView: View {
    @Environment(\.appTheme) private var theme
    let item: WatchlistItem

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(item.stockName)
                    .font(.headline)
                    .foregroundStyle(theme.primaryText)
                Text("\(item.stockCode) · \(item.market.marketDisplayName)")
                    .font(.caption)
                    .foregroundStyle(theme.secondaryText)
            }

            Spacer()
        }
        .padding(.vertical, 4)
    }
}

// ── ウォッチリスト行(マイページ用、SearchViewから移設) ───────────────

struct WatchlistRowView: View {
    @Environment(\.appTheme) private var theme
    let item: WatchlistItem
    let onRemove: () -> Void

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(item.stockName)
                    .font(.headline)
                    .foregroundStyle(theme.primaryText)
                Text("\(item.stockCode) · \(item.market.marketDisplayName)")
                    .font(.caption)
                    .foregroundStyle(theme.secondaryText)
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
