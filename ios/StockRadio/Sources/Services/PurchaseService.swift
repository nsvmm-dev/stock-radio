import Foundation
import StoreKit

@MainActor
final class PurchaseService: ObservableObject {
    static let productIds = [
        "com.stockradio.app.standard.monthly",
        "com.stockradio.app.pro.monthly",
    ]

    /// バックエンドの PRODUCT_PLAN_MAP と対応(表示上の現在プラン判定に使う)
    static func planName(for productId: String) -> String {
        switch productId {
        case "com.stockradio.app.standard.monthly": return "standard"
        case "com.stockradio.app.pro.monthly": return "pro"
        default: return "free"
        }
    }

    @Published var products: [Product] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    /// Transaction.updates の監視から購読者情報を反映する際に使う。
    /// MyPageView 表示時など、ユーザーIDが判明した時点でセットする。
    var userId: String?

    private var updatesTask: Task<Void, Never>?

    init() {
        updatesTask = startListeningForTransactionUpdates()
    }

    deinit {
        updatesTask?.cancel()
    }

    func loadProducts() async {
        do {
            products = try await Product.products(for: Self.productIds)
        } catch {
            errorMessage = "商品情報の取得に失敗しました: \(error.localizedDescription)"
        }
    }

    @discardableResult
    func purchase(_ product: Product, userId: String) async -> String? {
        isLoading = true
        defer { isLoading = false }
        do {
            let result = try await product.purchase()
            switch result {
            case .success(let verification):
                return await handle(verification: verification, userId: userId)
            case .userCancelled:
                return nil
            case .pending:
                errorMessage = "購入は保留中です(承認をお待ちください)"
                return nil
            @unknown default:
                return nil
            }
        } catch {
            errorMessage = "購入に失敗しました: \(error.localizedDescription)"
            return nil
        }
    }

    @discardableResult
    func restorePurchases(userId: String) async -> String? {
        isLoading = true
        defer { isLoading = false }
        do {
            try await AppStore.sync()
        } catch {
            errorMessage = "復元に失敗しました: \(error.localizedDescription)"
            return nil
        }
        return await syncCurrentEntitlement(userId: userId)
    }

    /// 現在有効なエンタイトルメントをバックエンドに反映する(有効なものがなければfreeへ降格)
    @discardableResult
    func syncCurrentEntitlement(userId: String) async -> String? {
        for await result in Transaction.currentEntitlements {
            guard case .verified(let transaction) = result,
                  Self.productIds.contains(transaction.productID) else { continue }
            return await report(transaction: transaction, userId: userId)
        }
        return try? await APIService.shared.updateSubscription(
            userId: userId, productId: nil, transactionId: nil, expiresAt: nil
        )
    }

    private func handle(verification: VerificationResult<Transaction>, userId: String) async -> String? {
        switch verification {
        case .verified(let transaction):
            let plan = await report(transaction: transaction, userId: userId)
            await transaction.finish()
            return plan
        case .unverified:
            errorMessage = "購入の検証に失敗しました"
            return nil
        }
    }

    private func report(transaction: Transaction, userId: String) async -> String? {
        let expiresAt = transaction.expirationDate.map { ISO8601DateFormatter().string(from: $0) }
        do {
            return try await APIService.shared.updateSubscription(
                userId: userId,
                productId: transaction.productID,
                transactionId: String(transaction.id),
                expiresAt: expiresAt
            )
        } catch {
            errorMessage = "プランの反映に失敗しました: \(error.localizedDescription)"
            return nil
        }
    }

    private func startListeningForTransactionUpdates() -> Task<Void, Never> {
        Task.detached { [weak self] in
            for await result in Transaction.updates {
                guard case .verified(let transaction) = result else { continue }
                await transaction.finish()
                guard let self else { continue }
                if let userId = await self.userId {
                    await self.report(transaction: transaction, userId: userId)
                }
            }
        }
    }
}
