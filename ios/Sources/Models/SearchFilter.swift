import Foundation

struct SearchFilter: Hashable {
    var keyword: String = ""
    var selectedLevels: Set<QuestionStudyState.MasteryLevel> = []
    var selectedRatings: Set<QuestionStudyState.QuestionRating> = []
    var selectedSetIDs: Set<String> = []

    var isEmpty: Bool {
        keyword.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        selectedLevels.isEmpty &&
        selectedRatings.isEmpty &&
        selectedSetIDs.isEmpty
    }
}
