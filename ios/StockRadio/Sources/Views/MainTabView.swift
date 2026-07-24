import SwiftUI

struct MainTabView: View {
    var body: some View {
        TabView {
            HomeDashboardView()
                .tabItem { Label("ホーム", systemImage: "house.fill") }
            DiscoverView()
                .tabItem { Label("検索", systemImage: "magnifyingglass") }
            MyPageView()
                .tabItem { Label("マイページ", systemImage: "person") }
        }
    }
}
