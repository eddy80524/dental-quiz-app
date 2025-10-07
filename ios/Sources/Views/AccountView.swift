import SwiftUI

struct AccountView: View {
    @ObservedObject var appData: AppData

    init(appData: AppData) {
        self.appData = appData
    }

    private var kokushiPurchases: [Int] {
        appData.profile.purchasedKokushiYears.sorted(by: >)
    }

    private var gakushiPurchases: [String] {
        appData.profile.purchasedGakushiSessions.sorted(by: >)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section(header: Text("ユーザー")) {
                    HStack {
                        Image(systemName: "person.crop.circle")
                            .font(.system(size: 42))
                            .foregroundColor(Color("AccentColor"))
                        VStack(alignment: .leading) {
                            Text(appData.profile.name)
                                .font(.headline)
                            Text(appData.profile.email)
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                    }
                    Label(appData.profile.membership.displayName, systemImage: "crown")
                        .foregroundColor(.secondary)
                }

                Section(header: Text("購入済みセット")) {
                    if kokushiPurchases.isEmpty && gakushiPurchases.isEmpty {
                        Text("購入済みの教材はありません")
                    } else {
                        if !kokushiPurchases.isEmpty {
                            DisclosureGroup("国試セット") {
                                ForEach(kokushiPurchases, id: \.self) { year in
                                    Text("\(year)回 国試パック")
                                }
                            }
                        }
                        if !gakushiPurchases.isEmpty {
                            DisclosureGroup("学士セット") {
                                ForEach(gakushiPurchases, id: \.self) { item in
                                    Text("学士 \(item)")
                                }
                            }
                        }
                    }
                }

                Section(header: Text("同期・バックアップ")) {
                    Button("購入を復元") {
                        // TODO: StoreKit連携
                    }
                    Button("学習データをエクスポート") {
                        // TODO: エクスポート処理
                    }
                }

                Section(header: Text("メモ・ブックマーク")) {
                    HStack {
                        Label("ブックマーク", systemImage: "bookmark")
                        Spacer()
                        Text("\(appData.bookmarks.count) 件")
                            .foregroundColor(.secondary)
                    }
                    HStack {
                        Label("メモ", systemImage: "note.text")
                        Spacer()
                        Text("\(appData.notes.count) 件")
                            .foregroundColor(.secondary)
                    }
                    HStack {
                        Label("履歴", systemImage: "clock.arrow.circlepath")
                        Spacer()
                        Text("\(appData.history.count) 問")
                            .foregroundColor(.secondary)
                    }
                }
            }
            .navigationTitle("アカウント")
        }
    }
}
