import SwiftUI
import FirebaseCore
import FirebaseMessaging
import UserNotifications

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
        }
    }
}

// ── アプリ全体の状態 ────────────────────────────────────────────────

@MainActor
final class AppState: ObservableObject {
    @Published var userId: String?
    @Published var plan: String = "free"
    @Published var radioLanguage: String = "ja"
    @Published var radioVoice: String = "mizuki"
    @Published var displayLanguage: String {
        didSet { UserDefaults.standard.set(displayLanguage, forKey: displayLanguageDefaultsKey) }
    }

    init() {
        displayLanguage = UserDefaults.standard.string(forKey: displayLanguageDefaultsKey) ?? "ja"
        if let user = LocalUser.load() {
            self.userId = user.userId
            self.plan = user.plan
            self.radioLanguage = user.radioLanguage ?? "ja"
            self.radioVoice = user.radioVoice ?? "mizuki"
        }
    }

    func signIn(userId: String, plan: String, radioLanguage: String, radioVoice: String = "mizuki") {
        self.userId = userId
        self.plan = plan
        self.radioLanguage = radioLanguage
        self.radioVoice = radioVoice
        LocalUser(userId: userId, plan: plan, radioLanguage: radioLanguage, radioVoice: radioVoice).save()
    }

    func updatePlan(_ plan: String) {
        self.plan = plan
        LocalUser(userId: userId ?? "", plan: plan, radioLanguage: radioLanguage, radioVoice: radioVoice).save()
    }

    func updateRadioLanguage(_ language: String) {
        self.radioLanguage = language
        LocalUser(userId: userId ?? "", plan: plan, radioLanguage: language, radioVoice: radioVoice).save()
    }

    func updateRadioVoice(_ voice: String) {
        self.radioVoice = voice
        LocalUser(userId: userId ?? "", plan: plan, radioLanguage: radioLanguage, radioVoice: voice).save()
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
