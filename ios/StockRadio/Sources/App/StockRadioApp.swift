import SwiftUI
import FirebaseCore
import FirebaseMessaging
import UserNotifications
import GoogleMobileAds

@main
struct StockRadioApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            Group {
                if appState.userId == nil {
                    OnboardingView()
                        .environmentObject(appState)
                } else {
                    MainTabView()
                        .environmentObject(appState)
                }
            }
            .environment(\.locale, Locale(identifier: appState.displayLanguage))
            .environment(\.appTheme, appState.uiTheme)
            .tint(appState.uiTheme.accent)
            .preferredColorScheme(appState.uiTheme.colorScheme)
        }
    }
}

let uiThemeDefaultsKey = "ui_theme"

// ── アプリ全体の状態 ────────────────────────────────────────────────

@MainActor
final class AppState: ObservableObject {
    @Published var userId: String?
    @Published var plan: String = "free"
    @Published var radioLanguage: String = defaultDisplayLanguage()
    @Published var displayLanguage: String {
        didSet { UserDefaults.standard.set(displayLanguage, forKey: displayLanguageDefaultsKey) }
    }
    @Published var uiTheme: AppTheme {
        didSet { UserDefaults.standard.set(uiTheme.rawValue, forKey: uiThemeDefaultsKey) }
    }

    init() {
        displayLanguage = UserDefaults.standard.string(forKey: displayLanguageDefaultsKey) ?? defaultDisplayLanguage()
        uiTheme = AppTheme(rawValue: UserDefaults.standard.string(forKey: uiThemeDefaultsKey) ?? "") ?? .standard
        if let user = LocalUser.load() {
            self.userId = user.userId
            self.plan = user.plan
            self.radioLanguage = user.radioLanguage ?? defaultDisplayLanguage()
        }
    }

    func signIn(userId: String, plan: String, radioLanguage: String) {
        self.userId = userId
        self.plan = plan
        self.radioLanguage = radioLanguage
        LocalUser(userId: userId, plan: plan, radioLanguage: radioLanguage).save()
    }

    func updatePlan(_ plan: String) {
        self.plan = plan
        LocalUser(userId: userId ?? "", plan: plan, radioLanguage: radioLanguage).save()
    }

    func updateRadioLanguage(_ language: String) {
        self.radioLanguage = language
        LocalUser(userId: userId ?? "", plan: plan, radioLanguage: language).save()
    }
}

// ── AppDelegate: Firebase + APNs ────────────────────────────────────

class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate, MessagingDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        // GoogleService-Info.plist がある場合のみ初期化（テスト環境では省略可）
        if Bundle.main.path(forResource: "GoogleService-Info", ofType: "plist") != nil {
            FirebaseApp.configure()
            Messaging.messaging().delegate = self
        }

        UNUserNotificationCenter.current().delegate = self
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound]) { _, _ in }
        application.registerForRemoteNotifications()

        GADMobileAds.sharedInstance().start(completionHandler: nil)

        return true
    }

    func messaging(_ messaging: Messaging, didReceiveRegistrationToken fcmToken: String?) {
        guard let token = fcmToken,
              let userId = LocalUser.load()?.userId else { return }

        Task {
            try? await APIService.shared.updateFCMToken(userId: userId, token: token)
        }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                 willPresent notification: UNNotification,
                                 withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound, .badge])
    }
}
