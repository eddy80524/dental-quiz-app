import SwiftUI

struct QuestionCardView: View {
    let question: Question
    @Binding var selectedIndices: [Int]
    let isAnswered: Bool
    @State private var shuffledIndices: [Int] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(question.question)
                .font(.title2)
                .padding(.bottom, 8)
            ForEach(shuffledIndices, id: \.self) { idx in
                Button(action: {
                    if isAnswered { return }
                    if selectedIndices.contains(idx) {
                        selectedIndices.removeAll { $0 == idx }
                    } else {
                        selectedIndices.append(idx)
                    }
                }) {
                    HStack {
                        Image(systemName: selectedIndices.contains(idx) ? "checkmark.square.fill" : "square")
                            .foregroundColor(Color("AccentColor"))
                        Text("\(String(UnicodeScalar(65 + idx)!)). \(question.choices[idx])")
                            .foregroundColor(.primary)
                    }
                    .padding()
                    .background(Color(.secondarySystemBackground))
                    .cornerRadius(8)
                }
                .disabled(isAnswered)
            }
            if let urls = question.imageUrls {
                ForEach(urls, id: \.self) { urlStr in
                    if let url = URL(string: urlStr) {
                        AsyncImage(url: url) { phase in
                            switch phase {
                            case .empty:
                                ProgressView()
                            case .success(let image):
                                image
                                    .resizable()
                                    .aspectRatio(contentMode: .fit)
                                    .frame(maxWidth: 320, maxHeight: 200)
                                    .cornerRadius(8)
                            case .failure:
                                Image(systemName: "photo")
                                    .resizable()
                                    .aspectRatio(contentMode: .fit)
                                    .frame(maxWidth: 120, maxHeight: 80)
                                    .foregroundColor(.gray)
                            @unknown default:
                                EmptyView()
                            }
                        }
                    } else {
                        Text("画像URL不正")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
        }
        .padding()
        .background(RoundedRectangle(cornerRadius: 16).fill(Color(.systemBackground)).shadow(radius: 2))
        .onAppear {
            // 選択肢を毎回シャッフル
            shuffledIndices = Array(question.choices.indices).shuffled()
            selectedIndices = [] // 問題切り替え時に選択リセット
        }
    }
}

struct QuestionCardView_Previews: PreviewProvider {
    static var previews: some View {
        let dummyQuestion = Question(
            id: "dummy",
            number: "Q1",
            question: "ダミー問題文",
            choices: ["選択肢A", "選択肢B", "選択肢C", "選択肢D", "選択肢E"],
            answer: "A",
            imageUrls: nil,
            sourceUrl: nil
        )
        QuestionCardView(question: dummyQuestion, selectedIndices: .constant([]), isAnswered: false)
    }
}
