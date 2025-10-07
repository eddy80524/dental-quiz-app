import Foundation
import Combine

@MainActor
final class AppData: ObservableObject {
    @Published private(set) var loadingState: LoadingState = .idle
    @Published private(set) var questions: [Question] = []
    @Published private(set) var questionCases: [String: QuestionCase] = [:]
    @Published private(set) var studySets: [StudySet] = []
    @Published private(set) var assignments: [StudyAssignment] = []
    @Published private(set) var activeSetProgress: [StudySetProgress] = []
    @Published private(set) var dailySummary: DailyStudySummary = DailyStudySummary(date: Date(), completed: 0, target: 0)

    @Published var profile: UserProfile = .placeholder
    @Published var questionStates: [String: QuestionStudyState] = [:]
    @Published var studySessions: [StudySessionLog] = []
    @Published var bookmarks: Set<String> = []
    @Published var notes: [String: String] = [:]
    @Published var history: [String] = []

    private let dataLoader: MasterDataLoader
    private let userDataService: UserDataService

    init(
        dataLoader: MasterDataLoader = .shared,
        userDataService: UserDataService = .shared
    ) {
        self.dataLoader = dataLoader
        self.userDataService = userDataService
        Task { await load() }
    }

    func reload() {
        Task { await load(force: true) }
    }

    private func load(force: Bool = false) async {
        guard force || loadingState != .loading else { return }
        loadingState = .loading
        do {
            let master = try await Task.detached(priority: .userInitiated) { () throws -> MasterData in
                try self.dataLoader.load()
            }.value

            let sets = StudySetBuilder.buildSets(from: master.questions)
            let snapshot = userDataService.loadInitialState(questions: master.questions, sets: sets)

            self.questions = master.questions
            self.questionCases = master.cases
            self.studySets = sets
            self.profile = snapshot.profile
            self.questionStates = Self.merge(states: snapshot.questionStates, withQuestions: master.questions)
            self.studySessions = snapshot.sessions
            self.activeSetProgress = Self.reconcile(progress: snapshot.activeSetProgress, sets: sets, states: questionStates)
            self.assignments = snapshot.assignments
            self.dailySummary = snapshot.dailySummary
            self.bookmarks = snapshot.bookmarks
            self.notes = snapshot.notes
            self.history = snapshot.history
            self.loadingState = .loaded
        } catch {
            self.loadingState = .failed(.init(error: error))
        }
    }

    private static func merge(states: [String: QuestionStudyState], withQuestions questions: [Question]) -> [String: QuestionStudyState] {
        var merged = states
        for question in questions {
            if merged[question.number] == nil {
                merged[question.number] = QuestionStudyState.placeholder(for: question.number)
            }
        }
        return merged
    }

    private static func reconcile(progress: [StudySetProgress], sets: [StudySet], states: [String: QuestionStudyState]) -> [StudySetProgress] {
        var results: [StudySetProgress] = []
        results.reserveCapacity(sets.count)

        let existing = Dictionary(uniqueKeysWithValues: progress.map { ($0.set.id, $0) })
        for set in sets {
            if let provided = existing[set.id] {
                results.append(provided)
                continue
            }
            let stats = set.questionNumbers.compactMap { states[$0] }
            let completed = stats.filter { $0.mastery == .mastered || $0.mastery == .level5 }.count
            let progressItem = StudySetProgress(
                set: set,
                completed: completed,
                total: max(stats.count, 1),
                nextDueDate: stats.compactMap { $0.lastStudiedAt }.sorted().first
            )
            results.append(progressItem)
        }

        return results.sorted { lhs, rhs in
            lhs.set.id < rhs.set.id
        }
    }

    // MARK: - User interaction helpers

    func toggleBookmark(for questionNumber: String) {
        if bookmarks.contains(questionNumber) {
            bookmarks.remove(questionNumber)
        } else {
            bookmarks.insert(questionNumber)
        }
    }

    func note(for questionNumber: String) -> String? {
        notes[questionNumber]
    }

    func updateNote(for questionNumber: String, text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            notes.removeValue(forKey: questionNumber)
        } else {
            notes[questionNumber] = trimmed
        }
    }

    func recordHistory(for questionNumber: String) {
        history.removeAll { $0 == questionNumber }
        history.insert(questionNumber, at: 0)
        if history.count > 200 {
            history = Array(history.prefix(200))
        }
    }
}
