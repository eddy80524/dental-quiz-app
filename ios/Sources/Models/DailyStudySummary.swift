import Foundation

struct DailyStudySummary: Codable, Hashable {
    var date: Date
    var completed: Int
    var target: Int

    var progress: Double {
        guard target > 0 else { return 0 }
        return Double(completed) / Double(target)
    }
}
