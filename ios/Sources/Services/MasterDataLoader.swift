import Foundation

struct MasterData {
    let questions: [Question]
    let cases: [String: QuestionCase]
}

final class MasterDataLoader {
    static let shared = MasterDataLoader()

    private let questionFileNames: [String] = [
        "master_questions_final.json",
        "gakushi-2022-1-1.json",
        "gakushi-2022-1-2.json",
        "gakushi-2022-1-3.json",
        "gakushi-2022-1再.json",
        "gakushi-2022-2.json",
        "gakushi-2023-1-1.json",
        "gakushi-2023-1-2.json",
        "gakushi-2023-1-3.json",
        "gakushi-2023-1再.json",
        "gakushi-2023-2.json",
        "gakushi-2023-2再.json",
        "gakushi-2024-1-1.json",
        "gakushi-2024-1-2.json",
        "gakushi-2024-2.json",
        "gakushi-2025-1-1.json",
        "gakushi-2025-1-2.json",
        "gakushi-2025-1-3.json"
    ]

    private let jsonDecoder: JSONDecoder

    init(jsonDecoder: JSONDecoder = MasterDataLoader.makeDecoder()) {
        self.jsonDecoder = jsonDecoder
    }

    func load() throws -> MasterData {
        var aggregatedQuestions: [Question] = []
        var aggregatedCases: [String: QuestionCase] = [:]
        var seenNumbers = Set<String>()

        for fileName in questionFileNames {
            guard let fileURL = locateDataFile(named: fileName) else {
                continue
            }
            do {
                let data = try Data(contentsOf: fileURL)
                let payload = try jsonDecoder.decode(QuestionsFileWrapper.self, from: data)
                for (caseID, questionCase) in payload.cases {
                    if aggregatedCases[caseID] == nil {
                        aggregatedCases[caseID] = questionCase
                    }
                }
                for question in payload.questions {
                    guard !question.number.isEmpty else { continue }
                    if seenNumbers.insert(question.number).inserted {
                        aggregatedQuestions.append(question)
                    }
                }
            } catch {
                throw LoadingError.fileDecodingFailed(fileName: fileName, underlying: error)
            }
        }

        aggregatedQuestions.sort { lhs, rhs in
            StudySet.sortQuestions(lhs.number, rhs.number)
        }

        return MasterData(questions: aggregatedQuestions, cases: aggregatedCases)
    }

    // MARK: - Private helpers

    private func locateDataFile(named fileName: String) -> URL? {
        let bundle = Bundle.main
        if let url = bundle.url(forResource: fileName, withExtension: nil, subdirectory: "data") {
            return url
        }

        let manager = FileManager.default
        let searchPaths: [String] = [
            "Resources/data/\(fileName)",
            "data/\(fileName)",
            "ios/Resources/data/\(fileName)",
            "functions/my_llm_app/data/\(fileName)",
            "my_llm_app/data/\(fileName)",
            fileName
        ]

        let currentDirectory = URL(fileURLWithPath: manager.currentDirectoryPath)
        for relativePath in searchPaths {
            let candidate = currentDirectory.appendingPathComponent(relativePath)
            if manager.fileExists(atPath: candidate.path) {
                return candidate
            }
        }
        return nil
    }

    private static func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }
}

extension MasterDataLoader {
    enum LoadingError: LocalizedError {
        case fileDecodingFailed(fileName: String, underlying: Error)

        var errorDescription: String? {
            switch self {
            case let .fileDecodingFailed(fileName, underlying):
                return "\(fileName) の読み込みに失敗しました: \(underlying.localizedDescription)"
            }
        }
    }
}

private struct QuestionsFileWrapper: Decodable {
    let cases: [String: QuestionCase]
    let questions: [Question]

    init(from decoder: Decoder) throws {
        if let arrayContainer = try? decoder.singleValueContainer(),
           let questionArray = try? arrayContainer.decode([Question].self) {
            self.questions = questionArray
            self.cases = [:]
            return
        }

        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.cases = try container.decodeIfPresent([String: QuestionCase].self, forKey: .cases) ?? [:]
        if let questions = try container.decodeIfPresent([Question].self, forKey: .questions) {
            self.questions = questions
        } else {
            self.questions = []
        }
    }

    enum CodingKeys: String, CodingKey {
        case cases
        case questions
    }
}
