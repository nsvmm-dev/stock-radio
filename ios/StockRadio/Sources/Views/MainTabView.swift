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
    }

    private func requestTrackingAuthorization() async {
        await withCheckedContinuation { continuation in
            ATTrackingManager.requestTrackingAuthorization { _ in
                continuation.resume()
            }
        }
    }
}
