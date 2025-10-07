import Foundation

struct Question: Identifiable, Codable, Hashable {
    let id: String
    let number: String
    let question: String
    let choices: [String]
    let answer: String
    let subject: String?
    let imageURLs: [String]?
    let imagePaths: [String]?
    let sourceURL: String?
    let caseID: String?

    init(
        id: String = UUID().uuidString,
        number: String,
        question: String,
        choices: [String],
        answer: String,
        subject: String? = nil,
        imageURLs: [String]? = nil,
        imagePaths: [String]? = nil,
        sourceURL: String? = nil,
        caseID: String? = nil
    ) {
        self.id = id
        self.number = number
        self.question = question
        self.choices = choices
        self.answer = answer
        self.subject = subject
        self.imageURLs = imageURLs
        self.imagePaths = imagePaths
        self.sourceURL = sourceURL
        self.caseID = caseID
    }

    enum CodingKeys: String, CodingKey {
        case id
        case number
        case question
        case choices
        case answer
        case subject
        case imageURLs = "image_urls"
        case imagePaths = "image_paths"
        case sourceURL = "source_url"
        case caseID = "case_id"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let decodedID = try container.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        let number = try container.decode(String.self, forKey: .number)
        let question = try container.decode(String.self, forKey: .question)
        let choices = try container.decode([String].self, forKey: .choices)
        let answer = try container.decode(String.self, forKey: .answer)
        let subject = try container.decodeIfPresent(String.self, forKey: .subject)
        let imageURLs = try container.decodeIfPresent([String].self, forKey: .imageURLs)
        let imagePaths = try container.decodeIfPresent([String].self, forKey: .imagePaths)
        let sourceURL = try container.decodeIfPresent(String.self, forKey: .sourceURL)
        let caseID = try container.decodeIfPresent(String.self, forKey: .caseID)

        self.init(
            id: decodedID,
            number: number,
            question: question,
            choices: choices,
            answer: answer,
            subject: subject,
            imageURLs: imageURLs,
            imagePaths: imagePaths,
            sourceURL: sourceURL,
            caseID: caseID
        )
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(number, forKey: .number)
        try container.encode(question, forKey: .question)
        try container.encode(choices, forKey: .choices)
        try container.encode(answer, forKey: .answer)
        try container.encodeIfPresent(subject, forKey: .subject)
        try container.encodeIfPresent(imageURLs, forKey: .imageURLs)
        try container.encodeIfPresent(imagePaths, forKey: .imagePaths)
        try container.encodeIfPresent(sourceURL, forKey: .sourceURL)
        try container.encodeIfPresent(caseID, forKey: .caseID)
    }

    var answerIndices: [Int] {
        answer
            .uppercased()
            .compactMap { $0.asciiValue }
            .map { Int($0 - Character("A").asciiValue!) }
    }

    var parsedNumber: QuestionNumber? {
        QuestionNumber(rawValue: number)
    }

    var isGakushi: Bool {
        parsedNumber?.kind.isGakushi ?? number.uppercased().hasPrefix("G")
    }
}
