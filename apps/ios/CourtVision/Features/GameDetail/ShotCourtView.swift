import SwiftUI

struct ShotCourtView: View {
    let points: [TimelinePoint]
    let selectedPoint: TimelinePoint?
    let onSelect: (TimelinePoint) -> Void

    private var shots: [TimelinePoint] {
        points.filter { $0.x != nil && $0.y != nil }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Shot Map")
                .font(.headline)

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

            if let selectedPoint, selectedPoint.x != nil {
                VStack(alignment: .leading, spacing: 3) {
                    Text(selectedPoint.description)
                        .font(.subheadline.weight(.semibold))
                    Text("Q\(selectedPoint.period) \(ScoreboardView.clock(selectedPoint.clockSeconds))")
                        .font(.caption.monospaced())
                        .foregroundStyle(CourtVisionTheme.muted)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(10)
                .background(CourtVisionTheme.raised)
            }
        }
        .courtVisionPanel()
    }

    private func position(for point: TimelinePoint, in size: CGSize) -> CGPoint {
        let x = size.width / 2 + CGFloat(point.x ?? 0) / 50 * size.width * 0.9
        let y = size.height * 0.08 + CGFloat(point.y ?? 0) / 47 * size.height * 0.82
        return CGPoint(x: x, y: y)
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
