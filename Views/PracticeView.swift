import SwiftUI

struct PracticeView: View {
    @StateObject private var viewModel = PracticeViewModel()

    var body: some View {
        VStack(spacing: 24) {
            if let question = viewModel.question {
                QuestionCardView(
                    question: question,
                    selectedIndices: $viewModel.selectedIndices,
                    isAnswered: viewModel.isAnswered
                )
                .padding(.horizontal)

                Button(action: {
                    viewModel.checkAnswer()
                }) {
                    Text("回答をチェック")
                        .font(.headline.bold())
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color("AccentColor"))
                        .foregroundColor(.white)
                        .cornerRadius(12)
                }
                .disabled(viewModel.isAnswered || viewModel.selectedIndices.isEmpty)
                .padding(.horizontal)

                if viewModel.isAnswered {
                    ResultDialogView(
                        isCorrect: viewModel.isCorrect,
                        correctChoices: viewModel.correctChoices,
                        selectedChoices: viewModel.selectedIndices.map { question.choices[$0] }
                    )
                    .padding(.top)
                    // --- 解説・フィードバック・自己評価履歴の表示 ---
                    if let explanation = question.explanation {
                        Text("解説: \(explanation)")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .padding(.top, 8)
                            .padding(.horizontal)
                    }
                    if let feedback = question.feedback {
                        Text("フィードバック: \(feedback)")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .padding(.horizontal)
                    }
                    if let selfAssessment = question.selfAssessment, !selfAssessment.isEmpty {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("自己評価履歴:")
                                .font(.subheadline.bold())
                            ForEach(selfAssessment, id: \.self) { item in
                                Text("・\(item)")
                                    .font(.caption)
                            }
                        }
                        .padding(.horizontal)
                    }
                }
            } else {
                ProgressView("読み込み中…")
            }
            Spacer()
        }
        .navigationTitle("演習")
        .onAppear { viewModel.loadQuestion() }
        .background(Color(.systemBackground))
    }
}

struct PracticeView_Previews: PreviewProvider {
    static var previews: some View {
        PracticeView()
    }
}


