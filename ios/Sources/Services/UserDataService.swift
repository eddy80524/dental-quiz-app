import Foundation

struct UserDataSnapshot {
    let profile: UserProfile
    let questionStates: [String: QuestionStudyState]
    let sessions: [StudySessionLog]
    let activeSetProgress: [StudySetProgress]
    let dailySummary: DailyStudySummary
    let assignments: [StudyAssignment]
    let bookmarks: Set<String>
    let notes: [String: String]
    let history: [String]
}

final class UserDataService {
    static let shared = UserDataService()

    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()
    private let storageFileName = "user_study_state.json"

    func loadInitialState(questions: [Question], sets: [StudySet]) -> UserDataSnapshot {
        if let persisted = try? loadFromDisk(sets: sets) {
            return persisted
        }
        return generateSampleData(questions: questions, sets: sets)
    }

    func save(snapshot: UserDataSnapshot) {
        let url = storageURL()
        let payload = PersistedSnapshot(snapshot: snapshot)
        do {
            let data = try encoder.encode(payload)
            try data.write(to: url, options: [.atomic])
        } catch {
            #if DEBUG
            print("[UserDataService] 保存に失敗: \(error)")
            #endif
        }
    }

    // MARK: - Private helpers

    private func storageURL() -> URL {
        let manager = FileManager.default
        let directory: URL
        if let docs = manager.urls(for: .documentDirectory, in: .userDomainMask).first {
            directory = docs
        } else {
            directory = URL(fileURLWithPath: manager.currentDirectoryPath)
        }
        return directory.appendingPathComponent(storageFileName)
    }

    private func loadFromDisk(sets: [StudySet]) throws -> UserDataSnapshot {
        let url = storageURL()
        let data = try Data(contentsOf: url)
        let persisted = try decoder.decode(PersistedSnapshot.self, from: data)
        return persisted.makeSnapshot(sets: sets)
    }

    private func generateSampleData(questions: [Question], sets: [StudySet]) -> UserDataSnapshot {
        let seedQuestions = Array(questions.prefix(1200))
        var questionStates: [String: QuestionStudyState] = [:]
        let calendar = Calendar(identifier: .gregorian)

        for question in seedQuestions {
            guard let parsed = question.parsedNumber else { continue }
            let base = pseudoRandom(for: question.number)
            let mastery = masterLevel(from: base)
            let rating = rating(from: base)
            let daysAgo = Int(base * 180)
            let lastStudied = calendar.date(byAdding: .day, value: -daysAgo, to: Date())
            let totalReviews = Int(3 + base * 20)
            let bestStreak = Int(1 + base * 8)
            let accuracy = 0.5 + Double(base) * 0.5

            questionStates[question.number] = QuestionStudyState(
                questionNumber: question.number,
                mastery: mastery,
                rating: rating,
                lastStudiedAt: lastStudied,
                totalReviews: totalReviews,
                bestStreak: bestStreak,
                accuracy: accuracy
            )
        }

        let activeSets = makeActiveSetProgress(sets: sets, questionStates: questionStates)
        let sessions = generateSampleSessions(activeSets: activeSets)
        let dailySummary = makeDailySummary(questionStates: questionStates)
        let profile = makeSampleProfile(activeSets: activeSets)
        let assignments = makeAssignments(activeSets: activeSets)
        let bookmarks = makeBookmarks(from: questionStates)
        let notes = makeNotes(from: questionStates)
        let history = makeHistory(from: questionStates)

        return UserDataSnapshot(
            profile: profile,
            questionStates: questionStates,
            sessions: sessions,
            activeSetProgress: activeSets,
            dailySummary: dailySummary,
            assignments: assignments,
            bookmarks: bookmarks,
            notes: notes,
            history: history
        )
    }

    private func masterLevel(from value: Double) -> QuestionStudyState.MasteryLevel {
        let ladder = QuestionStudyState.MasteryLevel.allCases
        let index = min(Int(value * Double(ladder.count)), ladder.count - 1)
        return ladder[index]
    }

    private func rating(from value: Double) -> QuestionStudyState.QuestionRating? {
        let ratings = QuestionStudyState.QuestionRating.allCases
        let idx = Int(value * Double(ratings.count))
        return ratings.indices.contains(idx) ? ratings[idx] : nil
    }

    private func makeActiveSetProgress(sets: [StudySet], questionStates: [String: QuestionStudyState]) -> [StudySetProgress] {
        let topSets = sets.prefix(8)
        let calendar = Calendar.current
        return topSets.map { set in
            let states = set.questionNumbers.compactMap { questionStates[$0] }
            let completed = states.filter { $0.mastery.numericValue >= QuestionStudyState.MasteryLevel.level3.numericValue }.count
            let total = max(states.count, 1)
            let dueDates = states.compactMap { state -> Date? in
                guard let last = state.lastStudiedAt else { return nil }
                let intervalDays = 7 - state.mastery.numericValue
                return calendar.date(byAdding: .day, value: max(intervalDays, 1), to: last)
            }
            let nextDue = dueDates.sorted().first
            return StudySetProgress(set: set, completed: completed, total: total, nextDueDate: nextDue)
        }
    }

    private func generateSampleSessions(activeSets: [StudySetProgress]) -> [StudySessionLog] {
        let calendar = Calendar.current
        var sessions: [StudySessionLog] = []
        for offset in 0..<28 {
            guard let day = calendar.date(byAdding: .day, value: -offset, to: Date()) else { continue }
            let sessionCount = offset % 3 == 0 ? 2 : 1
            for index in 0..<sessionCount {
                let base = Double((offset + 1) * (index + 1)) / 90.0
                guard let set = activeSets.randomElement() else { continue }
                let duration = 600 + Double(base * 900)
                let questions = 10 + Int(base * 20)
                let correct = Int(Double(questions) * (0.6 + base * 0.3))
                sessions.append(
                    StudySessionLog(
                        startedAt: calendar.date(byAdding: .minute, value: -(index * 90), to: day) ?? day,
                        duration: duration,
                        questionsAnswered: questions,
                        correctCount: min(correct, questions),
                        setID: set.id
                    )
                )
            }
        }
        return sessions.sorted { $0.startedAt > $1.startedAt }
    }

    private func makeDailySummary(questionStates: [String: QuestionStudyState]) -> DailyStudySummary {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        let completedToday = questionStates.values.filter { state in
            guard let last = state.lastStudiedAt else { return false }
            return calendar.isDate(last, inSameDayAs: today)
        }.count
        let target = 60
        return DailyStudySummary(date: today, completed: completedToday, target: target)
    }

    private func makeSampleProfile(activeSets: [StudySetProgress]) -> UserProfile {
        let years = activeSets.compactMap { progress -> Int? in
            if case let .kokushi(year, _) = progress.set.kind { return year }
            return nil
        }
        let sessions = activeSets.compactMap { progress -> String? in
            if case let .gakushi(year, session) = progress.set.kind { return "\(year)-\(session)" }
            return nil
        }
        return UserProfile(
            id: UUID(),
            name: "国試 太郎",
            email: "taro@example.com",
            level: 12,
            xp: 4320,
            streak: 18,
            membership: .premiumAnnual,
            purchasedKokushiYears: Array(Set(years)).sorted(by: >),
            purchasedGakushiSessions: sessions
        )
    }

    private func makeAssignments(activeSets: [StudySetProgress]) -> [StudyAssignment] {
        let calendar = Calendar.current
        return activeSets.prefix(3).enumerated().map { index, progress in
            let dueDate = calendar.date(byAdding: .day, value: index * 2 + 1, to: Date()) ?? Date()
            return StudyAssignment(
                set: progress.set,
                targetCount: 50,
                dueDate: dueDate,
                suggestedStartAt: calendar.date(byAdding: .hour, value: index * 2, to: Date()) ?? Date(),
                notes: "復習優先"
            )
        }
    }

    private func makeBookmarks(from states: [String: QuestionStudyState]) -> Set<String> {
        let sorted = states.values.sorted { (lhs, rhs) -> Bool in
            let leftDate = lhs.lastStudiedAt ?? .distantPast
            let rightDate = rhs.lastStudiedAt ?? .distantPast
            return leftDate > rightDate
        }
        return Set(sorted.prefix(40).map { $0.questionNumber })
    }

    private func makeNotes(from states: [String: QuestionStudyState]) -> [String: String] {
        let sampleNotes = [
            "根管治療時のポイントを再確認する",
            "写真を見て診断プロセスを言語化する",
            "補綴学の分類表を紙で暗記",
            "薬剤の用量をまとめ直す"
        ]
        let notedKeys = states.keys.prefix(sampleNotes.count)
        var notes: [String: String] = [:]
        for (key, note) in zip(notedKeys, sampleNotes) {
            notes[key] = note
        }
        return notes
    }

    private func makeHistory(from states: [String: QuestionStudyState]) -> [String] {
        states.values.sorted { (lhs, rhs) -> Bool in
            let leftDate = lhs.lastStudiedAt ?? .distantPast
            let rightDate = rhs.lastStudiedAt ?? .distantPast
            return leftDate > rightDate
        }
        .prefix(100)
        .map { $0.questionNumber }
    }

    private func pseudoRandom(for key: String) -> Double {
        var hasher = Hasher()
        hasher.combine(key)
        let value = hasher.finalize()
        let normalized = Double(abs(value % 10_000)) / 10_000.0
        return min(max(normalized, 0), 0.999)
    }
}

// MARK: - Persistence payload

private struct PersistedSnapshot: Codable {
    struct PersistedSetProgress: Codable {
        let setID: String
        let completed: Int
        let total: Int
        let nextDueDate: Date?
    }

    struct PersistedAssignment: Codable {
        let setID: String
        let targetCount: Int
        let dueDate: Date
        let suggestedStartAt: Date
        let notes: String?
    }

    let profile: UserProfile
    let questionStates: [String: QuestionStudyState]
    let sessions: [StudySessionLog]
    let setProgress: [PersistedSetProgress]
    let dailySummary: DailyStudySummary
    let assignments: [PersistedAssignment]
    let bookmarks: [String]
    let notes: [String: String]
    let history: [String]

    init(snapshot: UserDataSnapshot) {
        profile = snapshot.profile
        questionStates = snapshot.questionStates
        sessions = snapshot.sessions
        setProgress = snapshot.activeSetProgress.map { progress in
            PersistedSetProgress(
                setID: progress.set.id,
                completed: progress.completed,
                total: progress.total,
                nextDueDate: progress.nextDueDate
            )
        }
        dailySummary = snapshot.dailySummary
        assignments = snapshot.assignments.map { assignment in
            PersistedAssignment(
                setID: assignment.set.id,
                targetCount: assignment.targetCount,
                dueDate: assignment.dueDate,
                suggestedStartAt: assignment.suggestedStartAt,
                notes: assignment.notes
            )
        }
        bookmarks = Array(snapshot.bookmarks)
        notes = snapshot.notes
        history = snapshot.history
    }

    func makeSnapshot(sets: [StudySet]) -> UserDataSnapshot {
        let setDictionary = Dictionary(uniqueKeysWithValues: sets.map { ($0.id, $0) })
        let progress = setProgress.compactMap { item -> StudySetProgress? in
            guard let set = setDictionary[item.setID] else { return nil }
            return StudySetProgress(set: set, completed: item.completed, total: item.total, nextDueDate: item.nextDueDate)
        }
        let assignmentsModel = assignments.compactMap { item -> StudyAssignment? in
            guard let set = setDictionary[item.setID] else { return nil }
            return StudyAssignment(
                set: set,
                targetCount: item.targetCount,
                dueDate: item.dueDate,
                suggestedStartAt: item.suggestedStartAt,
                notes: item.notes
            )
        }
        return UserDataSnapshot(
            profile: profile,
            questionStates: questionStates,
            sessions: sessions,
            activeSetProgress: progress,
            dailySummary: dailySummary,
            assignments: assignmentsModel,
            bookmarks: Set(bookmarks),
            notes: notes,
            history: history
        )
    }
}
