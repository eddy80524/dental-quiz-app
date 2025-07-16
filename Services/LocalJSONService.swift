import Foundation

class LocalJSONService {
    static let shared = LocalJSONService()
    private init() {}

    func loadQuestions(from filename: String) -> [Question] {
        guard let url = Bundle.main.url(forResource: filename, withExtension: "json", subdirectory: "data") else {
            print("[LocalJSONService] ファイルが見つかりません: \(filename)")
            return []
        }
        do {
            let data = try Data(contentsOf: url)
            let decoder = JSONDecoder()
            let questions = try decoder.decode([Question].self, from: data)
            // --- バリデーション: 必須フィールドが欠けている場合は除外 ---
            let validQuestions = questions.filter { !$0.number.isEmpty && !$0.question.isEmpty && !$0.choices.isEmpty && !$0.answer.isEmpty }
            if validQuestions.count != questions.count {
                print("[LocalJSONService] 不正なデータを除外: \(questions.count - validQuestions.count)件")
            }
            return validQuestions
        } catch {
            print("[LocalJSONService] JSON読み込みエラー: \(error)")
            return []
        }
    }
}
