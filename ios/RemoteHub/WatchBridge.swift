import Foundation
import WatchConnectivity

/// Puente iPhone <-> Watch. El Watch intenta conectarse directo a la compu;
/// si no puede, manda sus comandos acá y el iPhone los reenvía por su WebSocket.
final class WatchBridge: NSObject, WCSessionDelegate {
    static let shared = WatchBridge()

    func start() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self
        WCSession.default.activate()
    }

    /// Le pasa al Watch host/puerto/token para que pueda conectarse directo.
    @MainActor func pushConfig() {
        guard WCSession.isSupported(), WCSession.default.activationState == .activated else { return }
        let hub = Hub.shared
        try? WCSession.default.updateApplicationContext([
            "host": hub.host, "port": hub.port, "token": hub.token,
            "shortcuts": hub.shortcuts, "presets": hub.presets,
        ])
    }

    func forwardClaude(text: String, done: Bool) {
        guard WCSession.isSupported(), WCSession.default.isReachable else { return }
        WCSession.default.sendMessage(["t": "claude.update", "text": String(text.suffix(1500)), "done": done],
                                      replyHandler: nil, errorHandler: nil)
    }

    func ack(_ action: String) {
        guard WCSession.isSupported(), WCSession.default.isReachable else { return }
        WCSession.default.sendMessage(["t": "phone.ack", "action": action], replyHandler: nil, errorHandler: nil)
    }

    // MARK: WCSessionDelegate

    func session(_ session: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {
        Task { @MainActor in self.pushConfig() }
    }

    func sessionDidBecomeInactive(_ session: WCSession) {}
    func sessionDidDeactivate(_ session: WCSession) { session.activate() }

    func sessionReachabilityDidChange(_ session: WCSession) {
        Task { @MainActor in self.pushConfig() }
    }

    func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        Task { @MainActor in
            if message["local"] as? String == "phone" {
                PhoneActions.shared.run(message)
                return
            }
            let t = message["t"] as? String ?? ""
            if t == "claude.run" || t == "claude.preset" { Hub.shared.beginClaude() }
            Hub.shared.send(message)
        }
    }
}
