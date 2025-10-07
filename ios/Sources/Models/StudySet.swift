import Foundation

struct StudySet: Identifiable, Hashable {
    enum Kind: Hashable {
        case kokushi(year: Int, category: QuestionNumber.KokushiCategory)
        case gakushi(year: Int, session: String)
    }

    let id: String
    let title: String
    let subtitle: String
    let kind: Kind
    let questionNumbers: [String]

    init(kind: Kind, questionNumbers: [String]) {
        self.kind = kind
        self.questionNumbers = questionNumbers.sorted(by: StudySet.sortQuestions)

        switch kind {
        case let .kokushi(year, category):
            self.title = "\(year)回 国試 \(category.rawValue)"
            self.subtitle = "全\(questionNumbers.count)問"
            self.id = "kokushi-\(year)-\(category.rawValue)"
        case let .gakushi(year, session):
            self.title = "学士\(year)年 \(session)"
            self.subtitle = "全\(questionNumbers.count)問"
            self.id = "gakushi-\(year)-\(session)"
        }
    }

    static func sortQuestions(_ lhs: String, _ rhs: String) -> Bool {
        let lhsInfo = QuestionNumber(rawValue: lhs)
        let rhsInfo = QuestionNumber(rawValue: rhs)
        switch (lhsInfo?.kind, rhsInfo?.kind) {
        case let (.kokushi(lyear, lblock, lindex), .kokushi(ryear, rblock, rindex)):
            if lyear != ryear { return lyear < ryear }
            if lblock != rblock { return lblock < rblock }
            return lindex < rindex
        case let (.gakushi(lyear, lsession, lblock, lindex, _), .gakushi(ryear, rsession, rblock, rindex, _)):
            if lyear != ryear { return lyear < ryear }
            if lsession != rsession { return lsession < rsession }
            if lblock != rblock { return lblock < rblock }
            return lindex < rindex
        case (.kokushi, .gakushi):
            return true
        case (.gakushi, .kokushi):
            return false
        case (.none, .some):
            return true
        case (.some, .none):
            return false
        case (.none, .none):
            return lhs < rhs
        }
    }
}

struct StudySetProgress: Identifiable, Hashable {
    let id: String
    let set: StudySet
    var completed: Int
    var total: Int
    var nextDueDate: Date?

    init(set: StudySet, completed: Int, total: Int, nextDueDate: Date?) {
        self.set = set
        self.completed = completed
        self.total = total
        self.nextDueDate = nextDueDate
        self.id = set.id
    }

    var completionRate: Double {
        guard total > 0 else { return 0 }
        return Double(completed) / Double(total)
    }
}

struct StudyAssignment: Identifiable, Hashable {
    let id: UUID
    let set: StudySet
    let targetCount: Int
    let dueDate: Date
    let suggestedStartAt: Date
    let notes: String?

    init(set: StudySet, targetCount: Int, dueDate: Date, suggestedStartAt: Date = Date(), notes: String? = nil) {
        self.id = UUID()
        self.set = set
        self.targetCount = targetCount
        self.dueDate = dueDate
        self.suggestedStartAt = suggestedStartAt
        self.notes = notes
    }
}
