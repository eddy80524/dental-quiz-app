import Foundation

enum LoadingState: Equatable {
    case idle
    case loading
    case loaded
    case failed(ErrorWrapper)

    struct ErrorWrapper: Identifiable, Equatable {
        let id = UUID()
        let error: Error
        let message: String

        init(error: Error, message: String) {
            self.error = error
            self.message = message
        }

        init(error: Error) {
            self.error = error
            self.message = error.localizedDescription
        }
    }
}
