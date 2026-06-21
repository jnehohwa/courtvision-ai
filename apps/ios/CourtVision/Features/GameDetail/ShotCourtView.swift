import SwiftUI

struct ShotCourtView: View {
    let points: [TimelinePoint]
    let selectedPoint: TimelinePoint?
    let shotQuality: ShotQualityResult?
    let shotQualityState: ShotQualityLoadState
    let shotQualityMessage: String?
    let shotQualityModelVersion: String
    let onSelect: (TimelinePoint) -> Void

    private var shots: [TimelinePoint] {
        points.filter { $0.x != nil && $0.y != nil }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Shot Map")
                .font(.headline)

            if let selectedPoint, selectedPoint.x != nil {
                selectedShotSummary(for: selectedPoint)
            }

            GeometryReader { proxy in
                ZStack {
                    CourtLines()
                    ForEach(shots) { point in
                        let position = position(for: point, in: proxy.size)
                        Button {
                            onSelect(point)
                        } label: {
                            Circle()
                                .fill(point.eventType == "shot_made" ? CourtVisionTheme.home : CourtVisionTheme.away)
                                .overlay {
                                    Circle()
                                        .stroke(.white, lineWidth: point.id == selectedPoint?.id ? 3 : 1)
                                }
                                .frame(
                                    width: point.id == selectedPoint?.id ? 18 : 13,
                                    height: point.id == selectedPoint?.id ? 18 : 13
                                )
                        }
                        .buttonStyle(.plain)
                        .position(position)
                        .accessibilityLabel(point.description)
                    }
                }
            }
            .aspectRatio(1.06, contentMode: .fit)
        }
        .courtVisionPanel()
    }

    private func position(for point: TimelinePoint, in size: CGSize) -> CGPoint {
        let x = size.width / 2 + CGFloat(point.x ?? 0) / 50 * size.width * 0.9
        let y = size.height * 0.08 + CGFloat(point.y ?? 0) / 47 * size.height * 0.82
        return CGPoint(x: x, y: y)
    }

    private func selectedShotSummary(for point: TimelinePoint) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(point.description)
                .font(.subheadline.weight(.semibold))
            Text("Q\(point.period) \(ScoreboardView.clock(point.clockSeconds))")
                .font(.caption.monospaced())
                .foregroundStyle(CourtVisionTheme.muted)

            Divider()
                .overlay(CourtVisionTheme.border)
                .padding(.vertical, 4)

            shotQualitySummary
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(CourtVisionTheme.raised)
    }

    @ViewBuilder
    private var shotQualitySummary: some View {
        switch shotQualityState {
        case .loading:
            Label("Calculating shooter-neutral shot quality...", systemImage: "chart.xyaxis.line")
                .font(.caption)
                .foregroundStyle(CourtVisionTheme.muted)
        case .loaded:
            if let shotQuality {
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 12) {
                        metric(
                            title: "xPTS",
                            value: shotQuality.expectedPoints.formatted(
                                .number.precision(.fractionLength(2))
                            )
                        )
                        metric(
                            title: "MAKE",
                            value: shotQuality.makeProbability.formatted(
                                .percent.precision(.fractionLength(0))
                            )
                        )
                        metric(title: "QUALITY", value: shotQuality.qualityLabel)
                    }
                    Text(shotQualityMessage ?? "Shooter-neutral location and game-context model.")
                        .font(.caption2)
                        .foregroundStyle(CourtVisionTheme.muted)
                    Text("\(shotQualityModelVersion) | no defender tracking")
                        .font(.caption2.monospaced())
                        .foregroundStyle(CourtVisionTheme.muted)
                }
            }
        case .failed:
            Label(
                shotQualityMessage ?? "Shot quality is temporarily unavailable.",
                systemImage: "exclamationmark.triangle"
            )
            .font(.caption)
            .foregroundStyle(CourtVisionTheme.away)
        case .unavailable:
            Text(shotQualityMessage ?? "Shot quality is unavailable for this event.")
                .font(.caption)
                .foregroundStyle(CourtVisionTheme.muted)
        }
    }

    private func metric(title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption2.monospaced())
                .foregroundStyle(CourtVisionTheme.muted)
            Text(value)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.primary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct CourtLines: View {
    var body: some View {
        Canvas { context, size in
            let border = Path(CGRect(origin: .zero, size: size).insetBy(dx: 1, dy: 1))
            context.stroke(border, with: .color(.white.opacity(0.5)), lineWidth: 1)

            let laneWidth = size.width * 0.36
            let lane = CGRect(
                x: (size.width - laneWidth) / 2,
                y: 0,
                width: laneWidth,
                height: size.height * 0.38
            )
            context.stroke(Path(lane), with: .color(.white.opacity(0.5)), lineWidth: 1)

            let freeThrow = CGRect(
                x: size.width * 0.38,
                y: size.height * 0.28,
                width: size.width * 0.24,
                height: size.width * 0.24
            )
            context.stroke(Path(ellipseIn: freeThrow), with: .color(.white.opacity(0.5)), lineWidth: 1)

            var arc = Path()
            arc.addArc(
                center: CGPoint(x: size.width / 2, y: size.height * 0.08),
                radius: size.width * 0.44,
                startAngle: .degrees(12),
                endAngle: .degrees(168),
                clockwise: false
            )
            context.stroke(arc, with: .color(.white.opacity(0.5)), lineWidth: 1)

            let rim = CGRect(
                x: size.width / 2 - 7,
                y: size.height * 0.07 - 7,
                width: 14,
                height: 14
            )
            context.stroke(Path(ellipseIn: rim), with: .color(.white.opacity(0.6)), lineWidth: 1)
        }
    }
}
