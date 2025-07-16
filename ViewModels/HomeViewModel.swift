import Foundation

class HomeViewModel: ObservableObject {
    @Published var progress: Double = 0

    func fetchProgress() {
        Task {
            let value = await ProgressService.shared.getProgress()
            await MainActor.run { self.progress = value }
        }
    }
}
