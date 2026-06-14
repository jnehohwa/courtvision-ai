import SwiftUI

struct MomentumView: View {
    let points: [TimelinePoint]
    let selectedPoint: TimelinePoint?
    let onSelect: (TimelinePoint) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Probability Timeline")
                .font(.headline)

            ScrollView(.horizontal) {
                LazyHStack(spacing: 10) {
                    ForEach(points) { point in
                        Button {
                            onSelect(point)
                        } label: {
                            VStack(alignment: .leading, spacing: 7) {
                                Text("Q\(point.period) \(ScoreboardView.clock(point.clockSeconds))")
                                    .font(.caption2.monospaced())
                                    .foregroundStyle(CourtVisionTheme.muted)
                                Text(point.description)
                                    .font(.caption.weight(.semibold))
                                    .lineLimit(2)
                                Text("\(point.homeScore) – \(point.awayScore)")
                                    .font(.caption.monospaced())
                                    .foregroundStyle(CourtVisionTheme.muted)
                            }
                            .frame(width: 150, height: 92, alignment: .topLeading)
                            .padding(10)
                            .background(CourtVisionTheme.raised)
                            .overlay {
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(
                                        point.id == selectedPoint?.id ? Color.white : CourtVisionTheme.border,
                                        lineWidth: point.id == selectedPoint?.id ? 2 : 1
                                    )
                            }
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .scrollIndicators(.hidden)
        }
        .courtVisionPanel()
    }
}
