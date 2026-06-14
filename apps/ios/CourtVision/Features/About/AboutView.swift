import SwiftUI

struct AboutView: View {
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
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
        }
        .navigationTitle("About")
    }
}
