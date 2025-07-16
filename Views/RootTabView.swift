import SwiftUI

struct RootTabView: View {
    var body: some View {
        TabView {
            HomeView()
                .tabItem {
                    Label("ホーム", systemImage: "house")
                }
            PracticeView()
                .tabItem {
                    Label("演習", systemImage: "pencil.and.outline")
                }
            SidebarView(evalStats: .mock)
                .tabItem {
                    Label("進捗", systemImage: "chart.bar")
                }
        }
        .accentColor(Color("AccentColor"))
    }
}

// TODO: HomeView, PracticeView, SidebarView, EvalStats.mock も順次作成

struct RootTabView_Previews: PreviewProvider {
    static var previews: some View {
        RootTabView()
    }
}
