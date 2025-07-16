import Foundation

class APIService {
    static let shared = APIService()
    private init() {}

    func fetchQuestion(id: String) async -> Question? {
        // TODO: 実際のAPIエンドポイントに合わせて実装
        guard let url = URL(string: "https://your-api.example.com/questions/\(id)") else { return nil }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            return try JSONDecoder().decode(Question.self, from: data)
        } catch {
            print("API error: \(error)")
            return nil
        }
    }
}
