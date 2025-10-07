import SwiftUI

struct TodayView: View {
    @ObservedObject var appData: AppData

    private var dailySummary: DailyStudySummary {
        appData.dailySummary
    }

    private var userProfile: UserProfile {
        appData.profile
    }

    private var assignments: [StudyAssignment] {
        appData.assignments
    }

    private var activeSets: [StudySetProgress] {
        appData.activeSetProgress
    }

    init(appData: AppData) {
        self.appData = appData
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    DailyProgressCard(summary: dailySummary)
                    userStatSection
                    assignmentsSection
                    activeSetsSection
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Today")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        appData.reload()
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            }
        }
    }

    private var userStatSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("学習ステータス")
                .font(.title2.bold())
            HStack(spacing: 16) {
                StatCard(title: "レベル", value: "Lv.\(userProfile.level)", subtitle: "XP \(userProfile.xp)", icon: "star.fill", color: .yellow)
                StatCard(title: "ストリーク", value: "\(userProfile.streak)日", subtitle: "継続中", icon: "flame.fill", color: .orange)
            }
        }
    }

    private var assignmentsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("今日の学習プラン")
                    .font(.title2.bold())
                Spacer()
                Button(action: appData.reload) {
                    Text("自動編成")
                }
                .buttonStyle(.bordered)
            }

            if assignments.isEmpty {
                Text("本日の学習プランはありません。")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            } else {
                VStack(spacing: 12) {
                    ForEach(assignments) { assignment in
                        AssignmentCard(assignment: assignment)
                    }
                }
            }
        }
    }

    private var activeSetsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("進行中のセット")
                .font(.title2.bold())
            if activeSets.isEmpty {
                RoundedRectangle(cornerRadius: 16)
                    .fill(Color(.secondarySystemGroupedBackground))
                    .frame(height: 120)
                    .overlay(
                        VStack(spacing: 8) {
                            Image(systemName: "tray")
                                .font(.title)
                                .foregroundStyle(.secondary)
                            Text("進捗中のセットがまだありません")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                    )
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 16) {
                        ForEach(activeSets) { progress in
                            StudySetProgressCard(progress: progress)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
    }
}

private struct DailyProgressCard: View {
    let summary: DailyStudySummary

    private var progress: Double {
        min(max(summary.progress, 0), 1)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("今日の学習進捗")
                    .font(.headline)
                Text("\(summary.completed)/\(summary.target) 問")
                    .font(.largeTitle.bold())
            }
            ProgressView(value: progress)
                .progressViewStyle(.linear)
                .tint(Color("AccentColor"))
            Button {
                // TODO: 画面遷移のルーティング実装
            } label: {
                Text("学習を始める")
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color("AccentColor"))
                    .foregroundStyle(.white)
                    .cornerRadius(12)
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(Color(.systemBackground))
                .shadow(color: Color.black.opacity(0.06), radius: 12, x: 0, y: 4)
        )
    }
}

private struct StatCard: View {
    let title: String
    let value: String
    let subtitle: String
    let icon: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: icon)
                    .font(.title2)
                    .foregroundStyle(color)
                Spacer()
            }
            Text(title)
                .font(.subheadline)
                .foregroundColor(.secondary)
            Text(value)
                .font(.title)
                .bold()
            Text(subtitle)
                .font(.footnote)
                .foregroundColor(.secondary)
        }
        .padding(16)
        .frame(maxWidth: .infinity)
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(Color(.systemBackground))
                .shadow(color: Color.black.opacity(0.05), radius: 8, x: 0, y: 3)
        )
    }
}

private struct AssignmentCard: View {
    let assignment: StudyAssignment
    private var dueFormatter: DateFormatter {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ja_JP")
        formatter.dateFormat = "M月d日(E)"
        return formatter
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(assignment.set.title)
                .font(.headline)
            Text("目標 \(assignment.targetCount)問 • 締切 \(dueFormatter.string(from: assignment.dueDate))")
                .font(.subheadline)
                .foregroundColor(.secondary)
            if let notes = assignment.notes {
                Text(notes)
                    .font(.footnote)
                    .foregroundColor(.secondary)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color(.secondarySystemGroupedBackground))
        )
    }
}

private struct StudySetProgressCard: View {
    let progress: StudySetProgress

    private var progressValue: Double { min(max(progress.completionRate, 0), 1) }

    private var subtitleText: String {
        switch progress.set.kind {
        case let .kokushi(year, category):
            return "\(year)回 • \(category.rawValue)"
        case let .gakushi(year, session):
            return "学士\(year)年 • \(session)"
        }
    }

    private var dueDateText: String {
        guard let dueDate = progress.nextDueDate else { return "次回復習未設定" }
        let formatter = RelativeDateTimeFormatter()
        formatter.locale = Locale(identifier: "ja_JP")
        formatter.unitsStyle = .full
        return formatter.localizedString(for: dueDate, relativeTo: Date())
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(progress.set.title)
                .font(.headline)
                .lineLimit(2)
            Text(subtitleText)
                .font(.subheadline)
                .foregroundColor(.secondary)
            ProgressView(value: progressValue)
                .tint(Color("AccentColor"))
            HStack {
                Text("\(progress.completed)/\(progress.total) 問")
                Spacer()
                Text(dueDateText)
            }
            .font(.caption)
            .foregroundColor(.secondary)
        }
        .padding(16)
        .frame(width: 240, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(Color(.systemBackground))
                .shadow(color: Color.black.opacity(0.05), radius: 8, x: 0, y: 3)
        )
    }
}
