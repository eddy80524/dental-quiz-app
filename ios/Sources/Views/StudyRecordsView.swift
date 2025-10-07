import SwiftUI
import Charts

struct StudyRecordsView: View {
    @ObservedObject var appData: AppData

    init(appData: AppData) {
        self.appData = appData
    }

    private var weeklySummaries: [PeriodSummary] {
        aggregateSessions(by: .weekOfYear, count: 8)
    }

    private var monthlySummaries: [PeriodSummary] {
        aggregateSessions(by: .month, count: 6)
    }

    private var studySetSummaries: [SetSummary] {
        let setsByID = Dictionary(uniqueKeysWithValues: appData.studySets.map { ($0.id, $0) })
        var accumulator: [String: (duration: TimeInterval, questions: Int)] = [:]
        for session in appData.studySessions {
            accumulator[session.setID, default: (0, 0)].duration += session.duration
            accumulator[session.setID, default: (0, 0)].questions += session.questionsAnswered
        }
        return accumulator.compactMap { key, value -> SetSummary? in
            guard let set = setsByID[key] else { return nil }
            return SetSummary(set: set, totalDuration: value.duration, totalQuestions: value.questions)
        }
        .sorted { $0.totalDuration > $1.totalDuration }
    }

    private var masteryDistribution: [MasteryDistribution] {
        var bucket: [QuestionStudyState.MasteryLevel: Int] = [:]
        for state in appData.questionStates.values {
            bucket[state.mastery, default: 0] += 1
        }
        return QuestionStudyState.MasteryLevel.allCases.map { level in
            MasteryDistribution(level: level, count: bucket[level] ?? 0)
        }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    SectionHeader(title: "週単位の学習時間", subtitle: weekComparisonText)
                    periodChart(data: weeklySummaries, highlight: true)

                    SectionHeader(title: "月間学習時間", subtitle: monthComparisonText)
                    periodChart(data: monthlySummaries, highlight: false)

                    SectionHeader(title: "セット別学習時間", subtitle: "国試と学士を切り替えて確認")
                    StudySetSummaryView(setSummaries: studySetSummaries, activeProgress: appData.activeSetProgress)

                    SectionHeader(title: "習熟度分布", subtitle: "未学習から習得済みまでの割合")
                    masteryDistributionView
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 16)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("学習記録")
        }
    }

    private func periodChart(data: [PeriodSummary], highlight: Bool) -> some View {
        Chart(data) { summary in
            BarMark(
                x: .value("期間", summary.label),
                y: .value("時間", summary.durationHours)
            )
            .foregroundStyle(summary.isLatest && highlight ? Color("AccentColor") : Color.accentColor.opacity(0.6))
        }
        .chartYAxisLabel("学習時間 (時間)")
        .chartXAxisLabel("期間")
        .frame(height: 220)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color(.systemBackground))
                .shadow(color: Color.black.opacity(0.05), radius: 8, x: 0, y: 3)
        )
    }

    private var masteryDistributionView: some View {
        Chart(masteryDistribution) { item in
            BarMark(
                x: .value("習熟度", item.level.rawValue),
                y: .value("問題数", item.count)
            )
            .foregroundStyle(Color("AccentColor"))
        }
        .frame(height: 200)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color(.systemBackground))
                .shadow(color: Color.black.opacity(0.05), radius: 8, x: 0, y: 3)
        )
    }

    private func aggregateSessions(by component: Calendar.Component, count: Int) -> [PeriodSummary] {
        let calendar = Calendar.current
        let now = Date()
        var summaries: [PeriodSummary] = []
        for index in 0..<count {
            guard let start = calendar.date(byAdding: component, value: -index, to: now)?.start(of: component, calendar: calendar) else { continue }
            let end = calendar.date(byAdding: component, value: 1, to: start) ?? now
            let filtered = appData.studySessions.filter { $0.startedAt >= start && $0.startedAt < end }
            let duration = filtered.reduce(0) { $0 + $1.duration }
            let questions = filtered.reduce(0) { $0 + $1.questionsAnswered }
            summaries.append(PeriodSummary(startDate: start, endDate: end, duration: duration, questions: questions, component: component))
        }
        return summaries.sorted { $0.startDate < $1.startDate }
    }

    private var weekComparisonText: String {
        comparisonText(for: weeklySummaries)
    }

    private var monthComparisonText: String {
        comparisonText(for: monthlySummaries)
    }

    private func comparisonText(for summaries: [PeriodSummary]) -> String {
        guard let latest = summaries.last, let previous = summaries.dropLast().last else {
            return "前期間データなし"
        }
        let diff = latest.duration - previous.duration
        let percent = previous.duration > 0 ? diff / previous.duration : 0
        let formatter = NumberFormatter()
        formatter.numberStyle = .percent
        formatter.maximumFractionDigits = 0
        let percentString = formatter.string(from: NSNumber(value: percent)) ?? "0%"
        let trend = diff >= 0 ? "+" : ""
        return "前期間比 \(trend)\(percentString)"
    }
}

private struct SectionHeader: View {
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.headline)
            Text(subtitle)
                .font(.footnote)
                .foregroundColor(.secondary)
        }
    }
}

private struct SetSummary: Identifiable {
    let id = UUID()
    let set: StudySet
    let totalDuration: TimeInterval
    let totalQuestions: Int

    var durationHours: Double { totalDuration / 3600 }

    var averageTimePerQuestion: Double {
        guard totalQuestions > 0 else { return 0 }
        return totalDuration / Double(totalQuestions)
    }
}

private struct StudySetSummaryView: View {
    let setSummaries: [SetSummary]
    let activeProgress: [StudySetProgress]

    @State private var segment: Segment = .kokushi

    private enum Segment: String, CaseIterable, Identifiable {
        case kokushi = "国試"
        case gakushi = "学士"
        var id: String { rawValue }
    }

    private var filteredSummaries: [SetSummary] {
        let filtered = setSummaries.filter { summary in
            switch (segment, summary.set.kind) {
            case (.kokushi, .kokushi): return true
            case (.gakushi, .gakushi): return true
            default: return false
            }
        }
        return Array(filtered.prefix(6))
    }

    private func progress(for set: StudySet) -> StudySetProgress? {
        activeProgress.first { $0.set.id == set.id }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Picker("セグメント", selection: $segment) {
                ForEach(Segment.allCases) { item in
                    Text(item.rawValue).tag(item)
                }
            }
            .pickerStyle(.segmented)

            if filteredSummaries.isEmpty {
                Text("該当する学習ログがありません")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                ForEach(filteredSummaries) { summary in
                    HStack(alignment: .top, spacing: 12) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(summary.set.title)
                                .font(.subheadline.bold())
                            Text("総時間: \(summary.durationHours.formatted(.number.precision(.fractionLength(1))))時間")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text("平均: \(Int(summary.averageTimePerQuestion))秒/問")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                        if let progress = progress(for: summary.set) {
                            CircularProgressView(progress: progress.completionRate)
                                .frame(width: 44, height: 44)
                        }
                    }
                    .padding(12)
                    .background(RoundedRectangle(cornerRadius: 12).fill(Color(.secondarySystemGroupedBackground)))
                }
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color(.systemBackground))
                .shadow(color: Color.black.opacity(0.05), radius: 8, x: 0, y: 3)
        )
    }
}

private struct CircularProgressView: View {
    let progress: Double

    var body: some View {
        ZStack {
            Circle()
                .stroke(Color(.systemGray5), lineWidth: 6)
            Circle()
                .trim(from: 0, to: CGFloat(min(max(progress, 0), 1)))
                .stroke(Color("AccentColor"), style: StrokeStyle(lineWidth: 6, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Text(progress.formatted(.percent.precision(.fractionLength(0))))
                .font(.caption2)
        }
    }
}

private struct PeriodSummary: Identifiable {
    let id = UUID()
    let startDate: Date
    let endDate: Date
    let duration: TimeInterval
    let questions: Int
    let component: Calendar.Component

    var label: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ja_JP")
        switch component {
        case .month:
            formatter.dateFormat = "M月"
        case .weekOfYear:
            formatter.dateFormat = "M/d"
        default:
            formatter.dateFormat = "M/d"
        }
        return formatter.string(from: startDate)
    }

    var durationHours: Double { duration / 3600 }
    var isLatest: Bool { endDate >= Date() }
}

private struct MasteryDistribution: Identifiable {
    let id = UUID()
    let level: QuestionStudyState.MasteryLevel
    let count: Int
}

private extension Date {
    func start(of component: Calendar.Component, calendar: Calendar) -> Date {
        if let interval = calendar.dateInterval(of: component, for: self)?.start {
            return interval
        }
        switch component {
        case .weekOfYear:
            let weekday = calendar.component(.weekday, from: self)
            let diff = weekday - calendar.firstWeekday
            return calendar.date(byAdding: .day, value: -diff, to: self) ?? self
        case .month:
            let components = calendar.dateComponents([.year, .month], from: self)
            return calendar.date(from: components) ?? self
        default:
            return self
        }
    }
}
