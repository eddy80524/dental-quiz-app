import Foundation

struct QuestionNumber: Hashable {
    enum Kind: Hashable {
        case kokushi(year: Int, block: String, index: Int)
        case gakushi(year: Int, session: String, block: String, index: Int, isRetake: Bool)

        var isGakushi: Bool {
            switch self {
            case .gakushi:
                return true
            case .kokushi:
                return false
            }
        }
    }

    let rawValue: String
    let kind: Kind

    init?(rawValue: String) {
        let trimmed = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        if let kokushiMatch = QuestionNumber.kokushiRegex.firstMatch(in: trimmed, range: NSRange(location: 0, length: trimmed.count)) {
            guard let yearRange = Range(kokushiMatch.range(at: 1), in: trimmed),
                  let blockRange = Range(kokushiMatch.range(at: 2), in: trimmed),
                  let indexRange = Range(kokushiMatch.range(at: 3), in: trimmed) else {
                return nil
            }
            let year = Int(trimmed[yearRange]) ?? 0
            let block = String(trimmed[blockRange])
            let index = Int(trimmed[indexRange]) ?? 0
            self.rawValue = trimmed
            self.kind = .kokushi(year: year, block: block, index: index)
            return
        }

        if let gakushiMatch = QuestionNumber.gakushiRegex.firstMatch(in: trimmed, range: NSRange(location: 0, length: trimmed.count)) {
            guard let yearRange = Range(gakushiMatch.range(at: 1), in: trimmed),
                  let sessionRange = Range(gakushiMatch.range(at: 2), in: trimmed),
                  let blockRange = Range(gakushiMatch.range(at: 3), in: trimmed),
                  let indexRange = Range(gakushiMatch.range(at: 4), in: trimmed) else {
                return nil
            }
            let shortYear = Int(trimmed[yearRange]) ?? 0
            let sessionRaw = String(trimmed[sessionRange])
            let block = String(trimmed[blockRange])
            let index = Int(trimmed[indexRange]) ?? 0
            let isRetake = sessionRaw.contains("再")
            let convertedYear: Int
            if shortYear >= 90 {
                convertedYear = 1900 + shortYear
            } else {
                convertedYear = 2000 + shortYear
            }
            self.rawValue = trimmed
            self.kind = .gakushi(year: convertedYear, session: sessionRaw, block: block, index: index, isRetake: isRetake)
            return
        }

        return nil
    }

    var kokushiYear: Int? {
        if case let .kokushi(year, _, _) = kind {
            return year
        }
        return nil
    }

    var kokushiBlock: String? {
        if case let .kokushi(_, block, _) = kind {
            return block
        }
        return nil
    }

    var index: Int {
        switch kind {
        case let .kokushi(_, _, index), let .gakushi(_, _, _, index, _):
            return index
        }
    }

    var gakushiYear: Int? {
        if case let .gakushi(year, _, _, _, _) = kind {
            return year
        }
        return nil
    }

    var gakushiSession: String? {
        if case let .gakushi(_, session, _, _, _) = kind {
            return session
        }
        return nil
    }

    var block: String {
        switch kind {
        case let .kokushi(_, block, _), let .gakushi(_, _, block, _, _):
            return block
        }
    }

    var isHisshu: Bool {
        switch kind {
        case let .kokushi(year, block, index):
            switch year {
            case 101...102:
                return ["A", "B"].contains(block) && (1...25).contains(index)
            case 103...110:
                return ["A", "C"].contains(block) && (1...35).contains(index)
            case 111...118:
                return ["A", "B", "C", "D"].contains(block) && (1...20).contains(index)
            default:
                return false
            }
        case let .gakushi(_, _, _, index, _):
            return (1...20).contains(index)
        }
    }

    // MARK: - Private

    private static let kokushiRegex: NSRegularExpression = {
        try! NSRegularExpression(pattern: "^(\\d+)([A-D])(\\d+)$", options: [])
    }()

    private static let gakushiRegex: NSRegularExpression = {
        try! NSRegularExpression(pattern: "^G(\\d{2})-([\\d再-]+)-([A-D])-(\\d+)$", options: [])
    }()
}

extension QuestionNumber {
    enum KokushiCategory: String, CaseIterable {
        case hisshu = "必修"
        case general = "一般"
        case clinical = "臨床実地"
    }

    var kokushiCategory: KokushiCategory? {
        guard case let .kokushi(year, block, index) = kind else { return nil }
        if isHisshu {
            return .hisshu
        }
        if block == "D" {
            return .clinical
        }

        // 101-110 の臨床実地は C/D に混在するため、indexで判定
        if (year >= 101 && year <= 110) && block == "C" && index > 35 {
            return .clinical
        }
        return .general
    }
}

extension QuestionNumber {
    struct GakushiIdentifier: Hashable {
        let year: Int
        let session: String
        let block: String
        let isRetake: Bool
    }

    var gakushiIdentifier: GakushiIdentifier? {
        guard case let .gakushi(year, session, block, _, isRetake) = kind else { return nil }
        return GakushiIdentifier(year: year, session: session, block: block, isRetake: isRetake)
    }
}
