import SwiftUI

struct ResultDialogView: View {
    let isCorrect: Bool
    let correctChoices: [String]
    let selectedChoices: [String]

    var body: some View {
        VStack(spacing: 12) {
            Text(isCorrect ? "✓ 正解！" : "× 不正解…")
                .font(.title.bold())
                .foregroundColor(isCorrect ? .green : .red)
            Text("正解: " + correctChoices.joined(separator: " / "))
                .font(.body)
            if !isCorrect {
                Text("あなたの選択: " + selectedChoices.joined(separator: " / "))
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding()
        .background(RoundedRectangle(cornerRadius: 12).fill(Color(.systemBackground)).shadow(radius: 1))
    }
}

struct ResultDialogView_Previews: PreviewProvider {
    static var previews: some View {
        ResultDialogView(
            isCorrect: true,
            correctChoices: ["選択肢A", "選択肢E"],
            selectedChoices: ["選択肢A"]
        )
    }
}
