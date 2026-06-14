import SwiftUI

struct ModelsView: View {
    private let models = [
        ("Pregame", "Deterministic logistic benchmark", "pregame-logistic-baseline-1.0"),
        ("Shot quality", "Shooter-neutral location and context", "shot-quality-baseline-1.0"),
        ("Live win", "Game-state probability benchmark", "live-win-logistic-baseline-1.0"),
    ]

    var body: some View {
        List(models, id: \.0) { model in
            VStack(alignment: .leading, spacing: 4) {
                Text(model.0)
                    .font(.headline)
                Text(model.1)
                    .foregroundStyle(.secondary)
                Text(model.2)
                    .font(.caption.monospaced())
                    .foregroundStyle(CourtVisionTheme.home)
            }
            .padding(.vertical, 6)
        }
        .navigationTitle("Models")
    }
}
