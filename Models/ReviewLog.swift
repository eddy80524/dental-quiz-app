import Foundation

struct ReviewLog: Codable, Identifiable {
    var id: UUID = UUID()
    let date: Date
    let type: String      // "Learn", "Review", "Relearn"
    let rating: Int       // 1: ×, 2: △, 3: ◯, 4: ◎
    let interval: Double  // 日数（分・日・月で統一）
    let ease: Double      // Easeファクター（%）
    let time: Int         // 解答にかかった秒数
}
