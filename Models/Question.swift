import Foundation

struct Question: Identifiable, Codable {
    let id: String
    let number: String
    let question: String
    let choices: [String]
    let answer: String
    let imageUrls: [String]?
    let sourceUrl: String?
    // --- 追加: explanation, feedback, selfAssessment ---
    let explanation: String?
    let feedback: String?
    let selfAssessment: [String]?

    var answerIndices: [Int] {
        answer.compactMap { $0.asciiValue.map { Int($0 - 65) } }
    }
}
