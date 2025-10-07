import Foundation

struct QuestionStudyState: Codable, Hashable {
    enum MasteryLevel: String, Codable, CaseIterable, Identifiable {
        case notStarted = "未学習"
        case level0 = "レベル0"
        case level1 = "レベル1"
        case level2 = "レベル2"
        case level3 = "レベル3"
        case level4 = "レベル4"
        case level5 = "レベル5"
        case mastered = "習得済み"

        var id: String { rawValue }
        var numericValue: Int {
            switch self {
            case .notStarted: return 0
            case .level0: return 1
            case .level1: return 2
            case .level2: return 3
            case .level3: return 4
            case .level4: return 5
            case .level5: return 6
            case .mastered: return 7
            }
        }
    }

    enum QuestionRating: String, Codable, CaseIterable, Identifiable {
        case repeatAgain = "もう一度"
        case easy = "簡単"
        case normal = "普通"
        case hard = "難しい"

        var id: String { rawValue }
    }

    let questionNumber: String
    var mastery: MasteryLevel
    var rating: QuestionRating?
    var lastStudiedAt: Date?
    var totalReviews: Int
    var bestStreak: Int
    var accuracy: Double

    static func placeholder(for questionNumber: String) -> QuestionStudyState {
        QuestionStudyState(
            questionNumber: questionNumber,
            mastery: .notStarted,
            rating: nil,
            lastStudiedAt: nil,
            totalReviews: 0,
            bestStreak: 0,
            accuracy: 0
        )
    }
}
