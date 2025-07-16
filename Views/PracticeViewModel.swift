import Foundation

class PracticeViewModel: ObservableObject {
    @Published var question: Question?
    @Published var selectedIndices: [Int] = []
    @Published var isAnswered: Bool = false
    @Published var isCorrect: Bool = false
    @Published var correctChoices: [String] = []
    @Published var reviewLogs: [ReviewLog] = []
    @Published var nextReviewDate: Date? = nil

    func loadQuestion() {
        let questions = LocalJSONService.shared.loadQuestions(from: "dental_118A")
        guard !questions.isEmpty else {
            print("[PracticeViewModel] 問題データが空です")
            self.question = nil
            return
        }
        let random = questions.randomElement()!
        self.question = random
        self.selectedIndices = []
        self.isAnswered = false
        self.isCorrect = false
        self.correctChoices = []
    }

    func checkAnswer() {
        guard let q = question else { return }
        let correct = q.answerIndices.sorted() == selectedIndices.sorted()
        isCorrect = correct
        isAnswered = true
        correctChoices = q.answerIndices.map { q.choices[$0] }
        // --- SM2学習履歴登録例 ---
        let now = Date()
        let rating = isCorrect ? 4 : 2 // ◎ or △（例）
        let type = reviewLogs.isEmpty ? "Learn" : "Review"
        let timeSpent = 30 // TODO: 実際の解答時間を計測
        let (interval, ease) = SM2Service.shared.calculateNextInterval(history: reviewLogs + [ReviewLog(date: now, type: type, rating: rating, interval: 0, ease: 2.5, time: timeSpent)])
        let log = ReviewLog(date: now, type: type, rating: rating, interval: interval, ease: ease, time: timeSpent)
        reviewLogs.append(log)
        nextReviewDate = Calendar.current.date(byAdding: .day, value: Int(interval), to: now)
    }
}
