import Foundation

struct StudySetBuilder {
    static func buildSets(from questions: [Question]) -> [StudySet] {
        var kokushiGroups: [StudySet.Kind: [String]] = [:]
        var gakushiGroups: [StudySet.Kind: [String]] = [:]

        for question in questions {
            guard let number = question.parsedNumber else { continue }
            switch number.kind {
            case let .kokushi(year, _, _):
                let category = number.kokushiCategory ?? .general
                let key = StudySet.Kind.kokushi(year: year, category: category)
                kokushiGroups[key, default: []].append(question.number)
            case let .gakushi(year, session, _, _, _):
                let key = StudySet.Kind.gakushi(year: year, session: session)
                gakushiGroups[key, default: []].append(question.number)
            }
        }

        let kokushiSets = kokushiGroups.keys.sorted(by: sortKokushi).map { key in
            StudySet(kind: key, questionNumbers: kokushiGroups[key] ?? [])
        }
        let gakushiSets = gakushiGroups.keys.sorted(by: sortGakushi).map { key in
            StudySet(kind: key, questionNumbers: gakushiGroups[key] ?? [])
        }
        return kokushiSets + gakushiSets
    }

    static func sortKokushi(_ lhs: StudySet.Kind, _ rhs: StudySet.Kind) -> Bool {
        guard case let .kokushi(lYear, lCategory) = lhs else { return false }
        guard case let .kokushi(rYear, rCategory) = rhs else { return true }
        if lYear != rYear { return lYear > rYear }
        return lCategory.sortOrder < rCategory.sortOrder
    }

    static func sortGakushi(_ lhs: StudySet.Kind, _ rhs: StudySet.Kind) -> Bool {
        guard case let .gakushi(lYear, lSession) = lhs else { return false }
        guard case let .gakushi(rYear, rSession) = rhs else { return true }
        if lYear != rYear { return lYear > rYear }
        return lSession.localizedStandardCompare(rSession) == .orderedDescending
    }
}

private extension QuestionNumber.KokushiCategory {
    var sortOrder: Int {
        switch self {
        case .hisshu: return 0
        case .general: return 1
        case .clinical: return 2
        }
    }
}
