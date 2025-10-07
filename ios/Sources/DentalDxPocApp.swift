import SwiftUI

@main
struct DentalDxPocApp: App {
    @StateObject private var appData = AppData()

    var body: some Scene {
        WindowGroup {
            RootTabView()
                .environmentObject(appData)
        }
    }
}
