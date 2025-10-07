import SwiftUI

struct SearchView: View {
    @ObservedObject var appData: AppData

    @State private var filter = SearchFilter()
    @State private var noteDraft: String = ""
    @State private var noteTarget: Question?
    @State private var segment: Segment = .all
    @State private var showFilters = false

    private enum Segment: String, CaseIterable, Identifiable {
        case all = "全件"
        case bookmarks = "ブックマーク"
        case history = "履歴"

        var id: String { rawValue }
    }

    init(appData: AppData) {
        self.appData = appData
    }

    private var questionMap: [String: Question] {
        Dictionary(uniqueKeysWithValues: appData.questions.map { ($0.number, $0) })
    }

    private var questionToSets: [String: [StudySet]] {
        var mapping: [String: [StudySet]] = [:]
        for set in appData.studySets {
            for number in set.questionNumbers {
                mapping[number, default: []].append(set)
            }
        }
        return mapping
    }

    private var filteredQuestions: [Question] {
        let base: [Question]
        switch segment {
        case .all:
            base = appData.questions
        case .bookmarks:
            base = appData.bookmarks.compactMap { questionMap[$0] }
        case .history:
            base = appData.history.compactMap { questionMap[$0] }
        }

        let keyword = filter.keyword.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let filtered = base.filter { question in
            if !keyword.isEmpty {
                let combined = (question.question + " " + (question.subject ?? "")).lowercased()
                if !combined.contains(keyword) {
                    return false
                }
            }

            if !filter.selectedLevels.isEmpty {
                guard let state = appData.questionStates[question.number], filter.selectedLevels.contains(state.mastery) else {
                    return false
                }
            }

            if !filter.selectedRatings.isEmpty {
                guard let state = appData.questionStates[question.number], let rating = state.rating, filter.selectedRatings.contains(rating) else {
                    return false
                }
            }

            if !filter.selectedSetIDs.isEmpty {
                let sets = questionToSets[question.number] ?? []
                let ids = Set(sets.map { $0.id })
                if ids.isDisjoint(with: filter.selectedSetIDs) {
                    return false
                }
            }

            return true
        }

        if segment == .history {
            return filtered
        }

        return filtered.sorted { lhs, rhs in
            let left = appData.questionStates[lhs.number]?.lastStudiedAt ?? .distantPast
            let right = appData.questionStates[rhs.number]?.lastStudiedAt ?? .distantPast
            return left > right
        }
    }

    private var availableSets: [StudySet] {
        appData.studySets
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                filterBar
                Divider()
                List {
                    ForEach(filteredQuestions) { question in
                        QuestionResultRow(
                            question: question,
                            state: appData.questionStates[question.number],
                            sets: questionToSets[question.number] ?? [],
                            isBookmarked: appData.bookmarks.contains(question.number),
                            note: appData.note(for: question.number)
                        ) {
                            appData.toggleBookmark(for: question.number)
                        } onNote: {
                            noteTarget = question
                            noteDraft = appData.note(for: question.number) ?? ""
                        }
                        .contentShape(Rectangle())
                        .onTapGesture {
                            appData.recordHistory(for: question.number)
                        }
                    }
                }
                .listStyle(.plain)
            }
            .navigationTitle("検索")
        }
        .sheet(item: $noteTarget) { question in
            NavigationStack {
                VStack(alignment: .leading, spacing: 16) {
                    Text(question.question)
                        .font(.headline)
                        .padding(.top)
                    TextEditor(text: $noteDraft)
                        .frame(minHeight: 180)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(Color(.separator), lineWidth: 1)
                        )
                    Spacer()
                }
                .padding()
                .navigationTitle("メモを編集")
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("キャンセル") {
                            noteTarget = nil
                        }
                    }
                    ToolbarItem(placement: .confirmationAction) {
                        Button("保存") {
                            if let target = noteTarget {
                                appData.updateNote(for: target.number, text: noteDraft)
                            }
                            noteTarget = nil
                        }
                    }
                }
            }
        }
        .searchable(text: $filter.keyword, placement: .navigationBarDrawer(displayMode: .always), prompt: "キーワード検索")
    }

    private var filterBar: some View {
        VStack(spacing: 12) {
            Picker("セグメント", selection: $segment) {
                ForEach(Segment.allCases) { item in
                    Text(item.rawValue).tag(item)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    FilterToggleChip(title: "レベル", isActive: !filter.selectedLevels.isEmpty) {
                        showFilters = true
                    }
                    FilterToggleChip(title: "レーティング", isActive: !filter.selectedRatings.isEmpty) {
                        showFilters = true
                    }
                    FilterToggleChip(title: "セット", isActive: !filter.selectedSetIDs.isEmpty) {
                        showFilters = true
                    }
                    if !filter.isEmpty {
                        Button("リセット") {
                            filter = SearchFilter()
                        }
                        .buttonStyle(.bordered)
                    }
                }
                .padding(.horizontal)
            }
        }
        .padding(.vertical, 12)
        .background(Color(.systemGroupedBackground))
        .sheet(isPresented: $showFilters) {
            NavigationStack {
                Form {
                    Section("レベル") {
                        ForEach(QuestionStudyState.MasteryLevel.allCases) { level in
                            Toggle(isOn: Binding(
                                get: { filter.selectedLevels.contains(level) },
                                set: { newValue in
                                    if newValue {
                                        filter.selectedLevels.insert(level)
                                    } else {
                                        filter.selectedLevels.remove(level)
                                    }
                                }
                            )) {
                                Text(level.rawValue)
                            }
                        }
                    }
                    Section("レーティング") {
                        ForEach(QuestionStudyState.QuestionRating.allCases) { rating in
                            Toggle(isOn: Binding(
                                get: { filter.selectedRatings.contains(rating) },
                                set: { newValue in
                                    if newValue {
                                        filter.selectedRatings.insert(rating)
                                    } else {
                                        filter.selectedRatings.remove(rating)
                                    }
                                }
                            )) {
                                Text(rating.rawValue)
                            }
                        }
                    }
                    Section("セット") {
                        ForEach(availableSets) { set in
                            Toggle(isOn: Binding(
                                get: { filter.selectedSetIDs.contains(set.id) },
                                set: { newValue in
                                    if newValue {
                                        filter.selectedSetIDs.insert(set.id)
                                    } else {
                                        filter.selectedSetIDs.remove(set.id)
                                    }
                                }
                            )) {
                                Text(set.title)
                            }
                        }
                    }
                }
                .navigationTitle("フィルター")
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("閉じる") { showFilters = false }
                    }
                    ToolbarItem(placement: .confirmationAction) {
                        Button("適用") { showFilters = false }
                    }
                }
            }
        }
    }
}

private struct FilterToggleChip: View {
    let title: String
    let isActive: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Text(title)
                if isActive {
                    Image(systemName: "checkmark")
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(
                Capsule(style: .continuous)
                    .fill(isActive ? Color("AccentColor").opacity(0.15) : Color(.secondarySystemBackground))
            )
            .overlay(
                Capsule(style: .continuous)
                    .stroke(isActive ? Color("AccentColor") : Color.clear, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

private struct QuestionResultRow: View {
    let question: Question
    let state: QuestionStudyState?
    let sets: [StudySet]
    let isBookmarked: Bool
    let note: String?
    let onBookmark: () -> Void
    let onNote: () -> Void

    private var tagText: String {
        let setNames = sets.prefix(2).map { $0.title }
        return setNames.joined(separator: " / ")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(question.number)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(question.question)
                        .font(.body)
                        .lineLimit(3)
                }
                Spacer()
                Button(action: onBookmark) {
                    Image(systemName: isBookmarked ? "bookmark.fill" : "bookmark")
                        .foregroundColor(isBookmarked ? Color("AccentColor") : Color(.tertiaryLabel))
                }
            }
            if let subject = question.subject {
                Text(subject)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if !tagText.isEmpty {
                Text(tagText)
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Capsule().fill(Color(.secondarySystemGroupedBackground)))
            }
            if let note = note, !note.isEmpty {
                HStack(alignment: .top) {
                    Image(systemName: "note.text")
                        .font(.caption)
                        .foregroundColor(Color("AccentColor"))
                    Text(note)
                        .font(.caption)
                }
            }
            HStack {
                if let mastery = state?.mastery {
                    Label(mastery.rawValue, systemImage: "chart.bar.doc.horizontal")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                if let rating = state?.rating {
                    Label(rating.rawValue, systemImage: "hand.thumbsup")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                Spacer()
                Button("メモ") {
                    onNote()
                }
                .font(.caption)
            }
        }
        .padding(.vertical, 8)
    }
}
