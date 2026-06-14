import SwiftUI

enum CourtVisionTheme {
    static let background = Color(red: 0.043, green: 0.051, blue: 0.055)
    static let surface = Color(red: 0.067, green: 0.078, blue: 0.086)
    static let raised = Color(red: 0.086, green: 0.102, blue: 0.11)
    static let border = Color.white.opacity(0.2)
    static let muted = Color(red: 0.56, green: 0.59, blue: 0.59)
    static let home = Color(red: 0.72, green: 1.0, blue: 0.12)
    static let away = Color(red: 1.0, green: 0.44, blue: 0.38)
}

extension View {
    func courtVisionPanel() -> some View {
        padding(16)
            .background(CourtVisionTheme.surface)
            .overlay {
                RoundedRectangle(cornerRadius: 14)
                    .stroke(CourtVisionTheme.border, lineWidth: 1)
            }
            .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}
