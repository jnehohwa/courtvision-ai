import SwiftUI

struct AppView: View {
    let appModel: AppModel

    var body: some View {
        TabView {
            NavigationStack {
                GamesView(apiClient: appModel.apiClient)
            }
            .tabItem {
                Label("Games", systemImage: "sportscourt")
            }

            NavigationStack {
                ModelsView()
            }
            .tabItem {
                Label("Models", systemImage: "chart.xyaxis.line")
            }

            NavigationStack {
                AboutView()
            }
            .tabItem {
                Label("About", systemImage: "info.circle")
            }
        }
        .tint(CourtVisionTheme.home)
    }
}
