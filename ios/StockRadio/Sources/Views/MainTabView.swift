import SwiftUI
import AppTrackingTransparency

struct MainTabView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        VStack(spacing: 0) {
            TabView {
                HomeDashboardView()
                    .tabItem { Label("ホーム", systemImage: "house.fill") }
                DiscoverView()
                    .tabItem { Label("検索", systemImage: "magnifyingglass") }
                MyPageView()
                    .tabItem { Label("マイページ", systemImage: "person") }
            }

            if appState.plan != "pro" {
                BannerAdView()
                    .frame(height: 50)
            }
        }
        .task {
            if ATTrackingManager.trackingAuthorizationStatus == .notDetermined {
                await requestTrackingAuthorization()
            }
        }
        .onChange(of: appState.uiTheme, initial: true) { _, theme in
            applyBarAppearance(theme)
        }
    }

    private func requestTrackingAuthorization() async {
        await withCheckedContinuation { continuation in
            ATTrackingManager.requestTrackingAuthorization { _ in
                continuation.resume()
            }
        }
    }

    private func applyBarAppearance(_ theme: AppTheme) {
        if theme == .trading {
            let background = UIColor(theme.background)
            let accent = UIColor(theme.accent)

            let tabBarAppearance = UITabBarAppearance()
            tabBarAppearance.configureWithOpaqueBackground()
            tabBarAppearance.backgroundColor = background
            tabBarAppearance.stackedLayoutAppearance.selected.iconColor = accent
            tabBarAppearance.stackedLayoutAppearance.selected.titleTextAttributes = [.foregroundColor: accent]
            tabBarAppearance.stackedLayoutAppearance.normal.iconColor = accent.withAlphaComponent(0.5)
            tabBarAppearance.stackedLayoutAppearance.normal.titleTextAttributes = [.foregroundColor: accent.withAlphaComponent(0.5)]
            UITabBar.appearance().standardAppearance = tabBarAppearance
            UITabBar.appearance().scrollEdgeAppearance = tabBarAppearance

            let navBarAppearance = UINavigationBarAppearance()
            navBarAppearance.configureWithOpaqueBackground()
            navBarAppearance.backgroundColor = background
            navBarAppearance.titleTextAttributes = [.foregroundColor: accent]
            navBarAppearance.largeTitleTextAttributes = [.foregroundColor: accent]
            UINavigationBar.appearance().standardAppearance = navBarAppearance
            UINavigationBar.appearance().scrollEdgeAppearance = navBarAppearance
            UINavigationBar.appearance().compactAppearance = navBarAppearance
        } else {
            let tabBarAppearance = UITabBarAppearance()
            tabBarAppearance.configureWithDefaultBackground()
            UITabBar.appearance().standardAppearance = tabBarAppearance
            UITabBar.appearance().scrollEdgeAppearance = tabBarAppearance

            let navBarAppearance = UINavigationBarAppearance()
            navBarAppearance.configureWithDefaultBackground()
            UINavigationBar.appearance().standardAppearance = navBarAppearance
            UINavigationBar.appearance().scrollEdgeAppearance = navBarAppearance
            UINavigationBar.appearance().compactAppearance = navBarAppearance
        }
    }
}
