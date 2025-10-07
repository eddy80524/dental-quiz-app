import SwiftUI

struct RootTabView: View {
    @EnvironmentObject private var appData: AppData

    var body: some View {
        Group {
            switch appData.loadingState {
            case .idle, .loading:
                ProgressView("データを読み込み中…")
                    .progressViewStyle(.circular)
            case .failed(let errorWrapper):
                VStack(spacing: 16) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 48))
                        .foregroundColor(.orange)
                    Text("読み込みに失敗しました")
                        .font(.headline)
                    Text(errorWrapper.message)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    Button(action: appData.reload) {
                        Label("再読み込み", systemImage: "arrow.clockwise")
                    }
                    .buttonStyle(.borderedProminent)
                }
                .padding()
            case .loaded:
                TabView {
                    TodayView(appData: appData)
                        .tabItem {
                            Label("Today", systemImage: "sun.max")
                        }
                    DiscoverView(appData: appData)
                        .tabItem {
                            Label("見つける", systemImage: "square.grid.2x2")
                        }
                    StudyRecordsView(appData: appData)
                        .tabItem {
                            Label("学習記録", systemImage: "chart.bar.xaxis")
                        }
                    SearchView(appData: appData)
                        .tabItem {
                            Label("検索", systemImage: "magnifyingglass")
                        }
                    AccountView(appData: appData)
                        .tabItem {
                            Label("アカウント", systemImage: "person.crop.circle")
                        }
                }
            }
        }
        .tint(Color("AccentColor"))
    }
}

struct RootTabView_Previews: PreviewProvider {
    static var previews: some View {
        RootTabView()
            .environmentObject(AppData())
    }
}
