import Foundation

class ProgressService {
    static let shared = ProgressService()
    private init() {}

    func getProgress() async -> Double {
        // TODO: APIServiceから進捗取得
        return 42 // 仮値
    }
}
