import Charts
import SwiftUI

struct GameDetailView: View {
    let game: Game
    @State private var model: GameDetailModel

    init(game: Game, apiClient: APIClient) {
        self.game = game
        _model = State(initialValue: GameDetailModel(game: game, apiClient: apiClient))
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                ScoreboardView(
                    game: model.snapshot?.game ?? game,
                    point: model.selectedPoint,
                    sourceLabel: model.snapshot?.sourceLabel ?? "Historical replay",
                    modelVersion: model.liveModelVersion,
                    isStale: model.snapshot?.isStale ?? false,
                    freshnessSeconds: model.snapshot?.freshnessSeconds,
                    connectionState: model.connectionState.rawValue
                )

                ProbabilityTimeline(
                    points: model.timeline,
                    selectedPoint: model.selectedPoint,
                    onSelect: model.select
                )

                ShotCourtView(
                    points: model.timeline,
                    selectedPoint: model.selectedPoint,
                    onSelect: model.select
                )

                MomentumView(
                    points: Array(model.timeline.suffix(12)),
                    selectedPoint: model.selectedPoint,
                    onSelect: model.select
                )
            }
            .padding()
        }
        .background(CourtVisionTheme.background)
        .navigationTitle("\(game.homeTeam.abbreviation) vs \(game.awayTeam.abbreviation)")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await model.load()
        }
        .onDisappear {
            Task { await model.disconnect() }
        }
        .alert(
            "Connection update",
            isPresented: Binding(
                get: { model.errorMessage != nil },
                set: { if !$0 { model.errorMessage = nil } }
            )
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(model.errorMessage ?? "")
        }
    }
}

struct ScoreboardView: View {
    let game: Game
    let point: TimelinePoint?
    let sourceLabel: String
    let modelVersion: String
    let isStale: Bool
    let freshnessSeconds: Int?
    let connectionState: String

    private var probability: Double {
        point?.homeProbability ?? game.prediction?.homeProbability ?? 0.5
    }

    var body: some View {
        VStack(spacing: 16) {
            HStack {
                Label(sourceLabel, systemImage: "circle.fill")
                    .labelStyle(.titleAndIcon)
                    .font(.caption.monospaced())
                    .foregroundStyle(CourtVisionTheme.home)
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text(connectionState.capitalized)
                    Text(freshnessLabel)
                }
                .font(.caption.monospaced())
                .foregroundStyle(isStale ? CourtVisionTheme.away : CourtVisionTheme.muted)
            }

            HStack(alignment: .firstTextBaseline) {
                score(name: game.homeTeam.name, value: point?.homeScore ?? game.homeScore, color: CourtVisionTheme.home)
                Spacer()
                VStack(spacing: 4) {
                    Text("Q\(point?.period ?? game.period)")
                    Text(Self.clock(point?.clockSeconds ?? game.clockSeconds))
                }
                .font(.headline.monospaced())
                Spacer()
                score(name: game.awayTeam.name, value: point?.awayScore ?? game.awayScore, color: CourtVisionTheme.away)
            }

            HStack(alignment: .bottom) {
                VStack(alignment: .leading) {
                    Text("HOME WIN PROBABILITY")
                        .font(.caption2.monospaced())
                        .foregroundStyle(CourtVisionTheme.muted)
                    Text(probability, format: .percent.precision(.fractionLength(0)))
                        .font(.system(size: 48, weight: .bold, design: .rounded))
                        .foregroundStyle(CourtVisionTheme.home)
                }
                Spacer()
                Text(modelVersion)
                    .font(.caption.monospaced())
                    .foregroundStyle(CourtVisionTheme.muted)
            }

            ProbabilityBar(probability: probability)
        }
        .courtVisionPanel()
    }

    private func score(name: String, value: Int, color: Color) -> some View {
        VStack(alignment: .leading) {
            Text(name)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(color)
            Text(value, format: .number)
                .font(.system(size: 54, weight: .semibold, design: .rounded))
                .monospacedDigit()
        }
    }

    static func clock(_ seconds: Int) -> String {
        String(format: "%02d:%02d", seconds / 60, seconds % 60)
    }

    private var freshnessLabel: String {
        if sourceLabel == "Historical replay" {
            return "Replay fixture"
        }
        guard let freshnessSeconds else {
            return isStale ? "Source unavailable" : "Freshness unknown"
        }
        let age = freshnessSeconds < 60
            ? "\(freshnessSeconds)s"
            : "\(freshnessSeconds / 60)m"
        return "\(isStale ? "Stale" : "Updated") \(age) ago"
    }
}

private struct ProbabilityTimeline: View {
    let points: [TimelinePoint]
    let selectedPoint: TimelinePoint?
    let onSelect: (TimelinePoint) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Win Probability Over Time")
                .font(.headline)

            Chart(points) { point in
                AreaMark(
                    x: .value("Sequence", point.sequence),
                    y: .value("Home probability", point.homeProbability)
                )
                .foregroundStyle(CourtVisionTheme.home.opacity(0.1))
                LineMark(
                    x: .value("Sequence", point.sequence),
                    y: .value("Home probability", point.homeProbability)
                )
                .foregroundStyle(CourtVisionTheme.home)
                .lineStyle(.init(lineWidth: 2.5))
                if point.sequence == selectedPoint?.sequence {
                    PointMark(
                        x: .value("Sequence", point.sequence),
                        y: .value("Home probability", point.homeProbability)
                    )
                    .symbolSize(80)
                    .foregroundStyle(CourtVisionTheme.home)
                }
            }
            .chartYScale(domain: 0...1)
            .chartYAxis {
                AxisMarks(values: [0.25, 0.5, 0.75, 1]) { value in
                    AxisGridLine(stroke: StrokeStyle(dash: [3, 4]))
                    AxisValueLabel {
                        if let probability = value.as(Double.self) {
                            Text(probability, format: .percent)
                        }
                    }
                }
            }
            .chartXSelection(
                value: Binding(
                    get: { selectedPoint?.sequence },
                    set: { sequence in
                        guard let sequence,
                              let point = points.min(by: {
                                  abs($0.sequence - sequence) < abs($1.sequence - sequence)
                              })
                        else { return }
                        onSelect(point)
                    }
                )
            )
            .frame(height: 220)
        }
        .courtVisionPanel()
    }
}
