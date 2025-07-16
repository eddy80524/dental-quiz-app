import SwiftUI

struct HomeView: View {
    @StateObject private var viewModel = HomeViewModel()

    var body: some View {
        NavigationView {
            VStack(spacing: 32) {
                Text("歯科医師国家試験アプリ")
                    .font(.system(.largeTitle, design: .rounded).bold())
                    .foregroundColor(Color("AccentColor"))
                    .padding(.top, 40)

                ProgressView(value: viewModel.progress, total: 100)
                    .accentColor(Color("AccentColor"))
                    .padding(.horizontal)

                Text("進捗: \(Int(viewModel.progress))%")
                    .font(.title2)
                    .foregroundColor(.secondary)

                NavigationLink(destination: PracticeView()) {
                    Text("演習を始める")
                        .font(.headline.bold())
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color("AccentColor"))
                        .foregroundColor(.white)
                        .cornerRadius(12)
                }
                .padding(.horizontal)
                Spacer()
            }
            .background(Color(.systemBackground))
            .onAppear { viewModel.fetchProgress() }
        }
    }
}

struct HomeView_Previews: PreviewProvider {
    static var previews: some View {
        HomeView()
    }
}
