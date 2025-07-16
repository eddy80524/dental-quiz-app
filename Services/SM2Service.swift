import Foundation

class SM2Service {
    static let shared = SM2Service()
    private init() {}

    // 4段階評価: 1(×), 2(△), 3(◯), 4(◎)
    func calculateNextInterval(history: [ReviewLog]) -> (interval: Double, ease: Double) {
        var EF = 2.5
        var n = 0
        var I: Double = 0
        for h in history {
            let q = h.rating
            if n == 0 {
                I = q >= 3 ? 1 : 0
            } else if n == 1 {
                I = q >= 3 ? 6 : 0
            } else {
                I = round(I * EF)
            }
            EF = max(1.3, EF + (0.1 - Double(5 - q) * (0.08 + Double(5 - q) * 0.02)))
            n = q >= 3 ? n + 1 : 0
        }
        return (interval: I, ease: EF)
    }
}
