import Foundation

struct StudySessionLog: Codable, Identifiable, Hashable {
    let id: UUID
    var startedAt: Date
    var duration: TimeInterval
    var questionsAnswered: Int
    var correctCount: Int
    var setID: String

    var accuracy: Double {
        guard questionsAnswered > 0 else { return 0 }
        return Double(correctCount) / Double(questionsAnswered)
    }

    init(
        id: UUID = UUID(),
        startedAt: Date,
        duration: TimeInterval,
        questionsAnswered: Int,
        correctCount: Int,
        setID: String
    ) {
        self.id = id
        self.startedAt = startedAt
        self.duration = duration
        self.questionsAnswered = questionsAnswered
        self.correctCount = correctCount
        self.setID = setID
    }
}

extension Collection where Element == StudySessionLog {
    func totalDuration() -> TimeInterval {
        reduce(0) { $0 + $1.duration }
    }

    func totalQuestions() -> Int {
        reduce(0) { $0 + $1.questionsAnswered }
    }
}
