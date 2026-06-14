import SwiftUI

struct GamesView: View {
    let apiClient: APIClient
    @State private var model: GamesModel

    init(apiClient: APIClient) {
        self.apiClient = apiClient
        _model = State(initialValue: GamesModel(apiClient: apiClient))
    }

    var body: some View {
        Group {
            switch model.state {
            case .loading:
                ProgressView("Loading games")
            case .failed(let message):
                ContentUnavailableView {
                    Label("Games unavailable", systemImage: "wifi.exclamationmark")
                } description: {
                    Text(message)
                } actions: {
                    Button("Try Again") {
                        Task { await model.load() }
                    }
                }
            case .loaded(let games):
                ScrollView {
                    LazyVStack(spacing: 14) {
                        ForEach(games) { game in
                            NavigationLink(value: game) {
                                GameCard(game: game)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding()
                }
                .background(CourtVisionTheme.background)
                .navigationDestination(for: Game.self) { game in
                    GameDetailView(game: game, apiClient: apiClient)
                }
            }
        }
        .navigationTitle("Tonight's Games")
        .task {
            await model.load()
        }
        .refreshable {
            await model.load()
        }
    }
}

private struct GameCard: View {
    let game: Game

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text(game.sourceStatus == .replay ? "Historical replay" : "Delayed data")
                    .font(.caption.monospaced())
                    .foregroundStyle(CourtVisionTheme.home)
                Spacer()
                Text(game.status.capitalized)
                    .font(.caption.monospaced())
                    .foregroundStyle(CourtVisionTheme.muted)
            }

            HStack(alignment: .firstTextBaseline) {
                TeamScore(name: game.homeTeam.name, score: game.homeScore, color: CourtVisionTheme.home)
                Spacer()
                Text("vs")
                    .font(.caption.monospaced())
                    .foregroundStyle(CourtVisionTheme.muted)
                Spacer()
                TeamScore(name: game.awayTeam.name, score: game.awayScore, color: CourtVisionTheme.away)
            }

            ProbabilityBar(probability: game.prediction?.homeProbability ?? 0.5)
        }
        .courtVisionPanel()
    }
}

private struct TeamScore: View {
    let name: String
    let score: Int
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(name)
                .font(.headline)
                .foregroundStyle(color)
            Text(score, format: .number)
                .font(.system(size: 46, weight: .semibold, design: .rounded))
                .monospacedDigit()
        }
    }
}

struct ProbabilityBar: View {
    let probability: Double

    var body: some View {
        VStack(spacing: 6) {
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    CourtVisionTheme.away
                    CourtVisionTheme.home
                        .frame(width: proxy.size.width * probability)
                    Rectangle()
                        .fill(.white)
                        .frame(width: 2)
                        .offset(x: proxy.size.width * probability)
                }
            }
            .frame(height: 9)
            .clipShape(Capsule())

            HStack {
                Text(probability, format: .percent.precision(.fractionLength(0)))
                    .foregroundStyle(CourtVisionTheme.home)
                Spacer()
                Text(1 - probability, format: .percent.precision(.fractionLength(0)))
                    .foregroundStyle(CourtVisionTheme.away)
            }
            .font(.caption.monospaced())
        }
    }
}
