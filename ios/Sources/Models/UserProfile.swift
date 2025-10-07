import Foundation

struct UserProfile: Codable, Hashable {
    enum MembershipTier: String, Codable, CaseIterable {
        case free
        case premiumMonthly
        case premiumAnnual

        var displayName: String {
            switch self {
            case .free:
                return "フリープラン"
            case .premiumMonthly:
                return "プレミアム（月額）"
            case .premiumAnnual:
                return "プレミアム（年額）"
            }
        }
    }

    let id: UUID
    var name: String
    var email: String
    var level: Int
    var xp: Int
    var streak: Int
    var membership: MembershipTier
    var purchasedKokushiYears: [Int]
    var purchasedGakushiSessions: [String]

    static let placeholder = UserProfile(
        id: UUID(),
        name: "ゲストユーザー",
        email: "guest@example.com",
        level: 1,
        xp: 0,
        streak: 0,
        membership: .free,
        purchasedKokushiYears: [],
        purchasedGakushiSessions: []
    )
}
