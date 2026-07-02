import SwiftUI

struct AboutView: View {
    let apiClient: APIClient

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("CourtVision AI")
                    .font(.largeTitle.bold())
                Text(
                    "A replay-first basketball analytics portfolio app. "
                    + "Predictions are model estimates and not guarantees."
                )
                Text(
                    "Public builds use synthetic or curated replay fixtures. "
                    + "The app does not claim licensed low-latency data or official league affiliation."
                )
                .foregroundStyle(.secondary)

                VStack(alignment: .leading, spacing: 8) {
                    Text("Backend")
                        .font(.headline)
                    LabeledContent("Mode", value: apiClient.configurationLabel)
                    LabeledContent("REST", value: apiClient.baseURL.absoluteString)
                    LabeledContent(
                        "WebSocket",
                        value: apiClient
                            .webSocketURL(gameID: "cv-2026-bos-nyk", after: 0)
                            .deletingLastPathComponent()
                            .absoluteString
                    )
                    if apiClient.usesLocalBackend {
                        Text(
                            "A physical iPhone needs a hosted API URL. "
                            + "Localhost points at the phone itself."
                        )
                        .font(.caption)
                        .foregroundStyle(CourtVisionTheme.away)
                    }
                }
                .courtVisionPanel()
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
        }
        .navigationTitle("About")
    }
}
