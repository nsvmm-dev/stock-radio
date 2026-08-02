import SwiftUI
import GoogleMobileAds

// Googleが公開しているテスト用広告ユニットID(アカウント不要・常にfill)。
// 本番運用開始時に実際のAdMobアカウントで発行された広告ユニットIDへ差し替える。
private let adUnitID = "ca-app-pub-9133327305052109/1298357492"

struct BannerAdView: UIViewRepresentable {
    func makeUIView(context: Context) -> GADBannerView {
        let banner = GADBannerView(adSize: GADAdSizeBanner)
        banner.adUnitID = adUnitID
        banner.rootViewController = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap { $0.windows }
            .first { $0.isKeyWindow }?.rootViewController
        banner.load(GADRequest())
        return banner
    }

    func updateUIView(_ uiView: GADBannerView, context: Context) {}
}
