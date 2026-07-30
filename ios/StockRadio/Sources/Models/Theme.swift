import SwiftUI

enum AppTheme: String, CaseIterable, Codable {
    case standard
    case trading

    var displayName: String {
        self == .trading ? localized("トレーディング") : localized("スタンダード")
    }

    /// 画面全体の背景色(List/ScrollViewの背景に使用)
    var background: Color {
        self == .trading ? Color(red: 0.05, green: 0.05, blue: 0.05) : Color(uiColor: .systemGroupedBackground)
    }

    /// カード/行の背景色
    var cardBackground: Color {
        self == .trading ? Color(red: 0.1, green: 0.1, blue: 0.1) : Color(uiColor: .secondarySystemGroupedBackground)
    }

    /// 見出し・本文などの主要テキスト色
    var primaryText: Color {
        self == .trading ? Color(red: 0, green: 1, blue: 0.4) : .primary
    }

    /// 補足テキスト色
    var secondaryText: Color {
        self == .trading ? Color(red: 0, green: 1, blue: 0.4).opacity(0.6) : .secondary
    }

    /// ボタン・リンク・選択状態などのアクセントカラー
    var accent: Color {
        self == .trading ? Color(red: 0, green: 1, blue: 0.4) : .blue
    }

    var colorScheme: ColorScheme? {
        self == .trading ? .dark : nil
    }
}

private struct AppThemeKey: EnvironmentKey {
    static let defaultValue: AppTheme = .standard
}

extension EnvironmentValues {
    var appTheme: AppTheme {
        get { self[AppThemeKey.self] }
        set { self[AppThemeKey.self] = newValue }
    }
}
