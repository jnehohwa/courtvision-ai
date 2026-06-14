import Foundation
import Observation

@MainActor
@Observable
final class GamesModel {
    enum State {
        case loading
        case loaded([Game])
        case failed(String)
    }

    private let apiClient: APIClient
    var state: State = .loading

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    func load() async {
        state = .loading
        do {
            state = .loaded(try await apiClient.games())
        } catch is CancellationError {
            return
        } catch {
            state = .failed(error.localizedDescription)
        }
    }
}
