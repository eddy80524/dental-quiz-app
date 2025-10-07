import SwiftUI

struct DiscoverView: View {
    @ObservedObject var appData: AppData

    @State private var segment: Segment = .kokushi
    @State private var selectedLevels: Set<QuestionStudyState.MasteryLevel> = []
    @State private var selectedSubjects: Set<String> = []
    @State private var selectedRatings: Set<QuestionStudyState.QuestionRating> = []
    @State private var searchText: String = ""

    private let chipColumns = [GridItem(.adaptive(minimum: 96), spacing: 8)]

    private enum Segment: String, CaseIterable, Identifiable {
        case kokushi = "国試"
        case gakushi = "学士"

        var id: String { rawValue }
    }

    private var questionMap: [String: Question] {
        Dictionary(uniqueKeysWithValues: appData.questions.map { ($0.number, $0) })
    }

    init(appData: AppData) {
        self.appData = appData
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                pickerSection
                filterSection
                Divider()
                ScrollView {
                    LazyVStack(spacing: 16, pinnedViews: [.sectionHeaders]) {
                        ForEach(filteredSets) { set in
                            StudySetRow(
                                set: set,
                                questionStates: appData.questionStates,
                                questionMap: questionMap
                            )
                            .padding(.horizontal)
                        }
                    }
                    .padding(.vertical)
                }
            }
            .navigationTitle("見つける")
        }
        .searchable(text: $searchText, placement: .navigationBarDrawer(displayMode: .always), prompt: "セット名・キーワード")
    }

    private var pickerSection: some View {
        Picker("タブ", selection: $segment) {
            ForEach(Segment.allCases) { item in
                Text(item.rawValue).tag(item)
            }
        }
        .pickerStyle(.segmented)
        .padding([.horizontal, .top])
    }

    private var filterSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            DisclosureGroup("レベルフィルター") {
                LazyVGrid(columns: chipColumns, alignment: .leading, spacing: 8) {
                    ForEach(QuestionStudyState.MasteryLevel.allCases) { level in
                        FilterChip(title: level.rawValue, isSelected: selectedLevels.contains(level)) {
                            if selectedLevels.contains(level) {
                                selectedLevels.remove(level)
                            } else {
                                selectedLevels.insert(level)
                            }
                        }
                    }
                }
                .padding(.top, 4)
            }
            .disclosureGroupStyle(.automatic)

            DisclosureGroup("分野フィルター") {
                LazyVGrid(columns: chipColumns, alignment: .leading, spacing: 8) {
                    ForEach(Array(availableSubjects).sorted(), id: \.self) { subject in
                        FilterChip(title: subject, isSelected: selectedSubjects.contains(subject)) {
                            if selectedSubjects.contains(subject) {
                                selectedSubjects.remove(subject)
                            } else {
                                selectedSubjects.insert(subject)
                            }
                        }
                    }
                }
                .padding(.top, 4)
            }

            DisclosureGroup("レーティング") {
                LazyVGrid(columns: chipColumns, alignment: .leading, spacing: 8) {
                    ForEach(QuestionStudyState.QuestionRating.allCases) { rating in
                        FilterChip(title: rating.rawValue, isSelected: selectedRatings.contains(rating)) {
                            if selectedRatings.contains(rating) {
                                selectedRatings.remove(rating)
                            } else {
                                selectedRatings.insert(rating)
                            }
                        }
                    }
                }
                .padding(.top, 4)
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 12)
        .background(Color(.systemGroupedBackground))
    }

    private var filteredSets: [StudySet] {
        let baseSets = appData.studySets.filter { set in
            switch (segment, set.kind) {
            case (.kokushi, .kokushi): return true
            case (.gakushi, .gakushi): return true
            default: return false
            }
        }

        return baseSets.filter { set in
            applyFilters(to: set)
        }
        .sorted { lhs, rhs in
            lhs.title < rhs.title
        }
    }

    private func applyFilters(to set: StudySet) -> Bool {
        if !searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            let keyword = searchText.lowercased()
            if !set.title.lowercased().contains(keyword) && !set.subtitle.lowercased().contains(keyword) {
                return false
            }
        }

        let questions = set.questionNumbers.compactMap { questionMap[$0] }
        let states = set.questionNumbers.compactMap { appData.questionStates[$0] }

        if !selectedSubjects.isEmpty {
            let subjects = Set(questions.compactMap { $0.subject })
            if subjects.isDisjoint(with: selectedSubjects) {
                return false
            }
        }

        if !selectedLevels.isEmpty {
            let levels = Set(states.map { $0.mastery })
            if levels.isDisjoint(with: selectedLevels) {
                return false
            }
        }

        if !selectedRatings.isEmpty {
            let ratings = Set(states.compactMap { $0.rating })
            if ratings.isEmpty || ratings.isDisjoint(with: selectedRatings) {
                return false
            }
        }

        return true
    }

    private var availableSubjects: Set<String> {
        let filtered = appData.questions.filter { question in
            if let parsed = question.parsedNumber {
                switch (segment, parsed.kind) {
                case (.kokushi, .kokushi): return true
                case (.gakushi, .gakushi): return true
                default: return false
                }
            }
            return false
        }
        return Set(filtered.compactMap { $0.subject })
    }
}

private struct StudySetRow: View {
    let set: StudySet
    let questionStates: [String: QuestionStudyState]
    let questionMap: [String: Question]

    private var questions: [Question] {
        set.questionNumbers.compactMap { questionMap[$0] }
    }

    private var completionRate: Double {
        let states = set.questionNumbers.compactMap { questionStates[$0] }
        guard !states.isEmpty else { return 0 }
        let mastered = states.filter { $0.mastery == .mastered }.count
        return Double(mastered) / Double(states.count)
    }

    private var subjectList: String {
        let subjects = Set(questions.compactMap { $0.subject }).sorted()
        return subjects.joined(separator: " / ")
    }

    private var questionCountText: String {
        "全\(set.questionNumbers.count)問"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(set.title)
                        .font(.headline)
                    Text(subjectList.isEmpty ? "分野情報なし" : subjectList)
                        .font(.footnote)
                        .foregroundColor(.secondary)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .foregroundColor(Color(.tertiaryLabel))
            }
            ProgressView(value: completionRate)
                .tint(Color("AccentColor"))
            HStack {
                Badge(text: questionCountText, systemImage: "number")
                Spacer()
                Badge(text: completionRate.formatted(.percent.precision(.fractionLength(0))), systemImage: "checkmark.circle")
            }
            .font(.caption)
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color(.systemBackground))
                .shadow(color: Color.black.opacity(0.04), radius: 6, x: 0, y: 2)
        )
    }
}

private struct FilterChip: View {
    let title: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Text(title)
                if isSelected {
                    Image(systemName: "checkmark")
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(
                Capsule(style: .continuous)
                    .fill(isSelected ? Color("AccentColor").opacity(0.15) : Color(.secondarySystemBackground))
            )
            .overlay(
                Capsule(style: .continuous)
                    .stroke(isSelected ? Color("AccentColor") : Color.clear, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

private struct Badge: View {
    let text: String
    let systemImage: String

    var body: some View {
        Label(text, systemImage: systemImage)
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(
                Capsule(style: .continuous)
                    .fill(Color(.secondarySystemBackground))
            )
    }
}
