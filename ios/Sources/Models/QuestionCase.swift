import Foundation

struct QuestionCase: Codable, Hashable {
    let scenarioText: String
    let imageURLs: [String]?

    enum CodingKeys: String, CodingKey {
        case scenarioText = "scenario_text"
        case imageURLs = "image_urls"
    }
}
