import SwiftUI

@main
struct CourtVisionApp: App {
    @State private var appModel = AppModel()

    var body: some Scene {
        WindowGroup {
            AppView(appModel: appModel)
                .preferredColorScheme(.dark)
        }
    }
}
