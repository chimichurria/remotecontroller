import SwiftUI

@main
struct RemoteHubApp: App {
    @StateObject private var hub = Hub.shared
    @Environment(\.scenePhase) private var phase

    init() { WatchBridge.shared.start() }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(hub)
                .onOpenURL { hub.handle(url: $0) }
                .task {
                    hub.startBrowsing()
                    if hub.hasSaved { hub.connect() }
                }
                .onChange(of: phase) { _, new in
                    if new == .active { hub.reconnectIfNeeded() }
                }
                // Con la compu conectada, la pantalla no se apaga: iOS suspende la app en segundo plano.
                .onChange(of: hub.status) { _, s in
                    UIApplication.shared.isIdleTimerDisabled = s.isConnected
                }
        }
    }
}
