import Foundation
import Observation

@MainActor
@Observable
final class AppModel {
    let apiClient: APIClient

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }
}
