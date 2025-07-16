import SwiftUI

struct SidebarView: View {
    let evalStats: EvalStats

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("自己評価の分布")
                .font(.headline)
                .padding(.bottom, 4)
            Text("合計演習数: \(evalStats.total)問")
                .font(.subheadline)
                .bold()
            ForEach(evalStats.items, id: \.label) { stat in
                HStack {
                    Text("\(stat.icon) \(stat.label):")
                    Text("\(stat.count)問 (\(stat.percent)%)")
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding()
        .background(RoundedRectangle(cornerRadius: 12).fill(Color(.secondarySystemBackground)))
        .padding(.horizontal)
    }
}

struct EvalStats {
    struct Item {
        let label: String
        let icon: String
        let count: Int
        let percent: Int
    }
    let total: Int
    let items: [Item]

    static var mock: EvalStats {
        EvalStats(
            total: 0,
            items: [
                .init(label: "もう一度", icon: "×", count: 0, percent: 0),
                .init(label: "難しい", icon: "△", count: 0, percent: 0),
                .init(label: "普通", icon: "◯", count: 0, percent: 0),
                .init(label: "簡単", icon: "◎", count: 0, percent: 0)
            ]
        )
    }
}

struct SidebarView_Previews: PreviewProvider {
    static var previews: some View {
        SidebarView(evalStats: .mock)
    }
}
