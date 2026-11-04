import Foundation
import WatchConnectivity
import WatchKit

/// Transporte del Watch: intenta WebSocket directo a la compu (Wi-Fi);
/// si no se puede, reenvía todo al iPhone con WatchConnectivity.
final class WatchLink: NSObject, ObservableObject, WCSessionDelegate {
    static let shared = WatchLink()

    @Published var mode = "conectando…"
    @Published var claudeText = ""
    @Published var claudeBusy = false
    @Published var shortcuts: [String] = []
    @Published var presets: [String] = ["tests", "status", "review"]

    private var host = "", token = ""
    private var port = 8765
    private var task: URLSessionWebSocketTask?
    private var directReady = false
    private let session = URLSession(configuration: .default)
    private var retryWork: DispatchWorkItem?

    func start() {
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
        applyContext(WCSession.default.receivedApplicationContext)
        connectDirect()
    }

    // MARK: Conexión directa

    func connectDirect() {
        guard !host.isEmpty, !token.isEmpty, let url = URL(string: "ws://\(host):\(port)/ws") else {
            updateMode(); return
        }
        task?.cancel(with: .goingAway, reason: nil)
        directReady = false
        let t = session.webSocketTask(with: url)
        task = t
        t.resume()
        raw(["t": "hello", "token": token, "name": "Apple Watch", "role": "controller"])
        listen(t)
    }

    private func listen(_ t: URLSessionWebSocketTask) {
        t.receive { [weak self] result in
            DispatchQueue.main.async {
                guard let self, self.task === t else { return }
                switch result {
                case .failure:
                    self.directReady = false
                    self.updateMode()
                    self.scheduleRetry()
                case .success(let msg):
                    if case .string(let s) = msg { self.handle(s) }
                    self.listen(t)
                }
            }
        }
    }

    private func scheduleRetry() {
        retryWork?.cancel()
        let w = DispatchWorkItem { [weak self] in self?.connectDirect() }
        retryWork = w
        DispatchQueue.main.asyncAfter(deadline: .now() + 5, execute: w)
    }

    private func handle(_ s: String) {
        guard let d = s.data(using: .utf8),
              let m = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
              let t = m["t"] as? String else { return }
        switch t {
        case "ready": directReady = true; updateMode()
        case "error":
            if m["code"] != nil { directReady = false; task?.cancel(with: .goingAway, reason: nil); updateMode() }
        case "claude.output": claudeText += m["chunk"] as? String ?? ""
        case "claude.done":
            claudeBusy = false
            if let text = m["text"] as? String, !text.isEmpty { claudeText = text }
            WKInterfaceDevice.current().play(.success)
        default: break
        }
    }

    private func updateMode() {
        if directReady { mode = "directo" }
        else if WCSession.isSupported() && WCSession.default.isReachable { mode = "vía iPhone" }
        else { mode = "sin conexión" }
    }

    // MARK: Envío

    private func raw(_ obj: [String: Any]) {
        guard let d = try? JSONSerialization.data(withJSONObject: obj),
              let s = String(data: d, encoding: .utf8) else { return }
        task?.send(.string(s)) { _ in }
    }

    /// Comandos para la compu.
    func send(_ obj: [String: Any]) {
        if directReady { raw(obj) }
        else if WCSession.isSupported(), WCSession.default.isReachable {
            WCSession.default.sendMessage(obj, replyHandler: nil, errorHandler: nil)
        }
    }

    /// Comandos para el iPhone (siempre por WatchConnectivity).
    func sendPhone(_ action: String, name: String? = nil) {
        guard WCSession.isSupported(), WCSession.default.isReachable else { return }
        var m: [String: Any] = ["local": "phone", "action": action]
        if let name { m["name"] = name }
        WCSession.default.sendMessage(m, replyHandler: nil, errorHandler: nil)
    }

    func claude(text: String) {
        claudeText = ""; claudeBusy = true
        send(["t": "claude.run", "text": text])
    }

    func claudePreset(_ name: String) {
        claudeText = ""; claudeBusy = true
        send(["t": "claude.preset", "name": name])
    }

    // MARK: WCSessionDelegate

    private func applyContext(_ c: [String: Any]) {
        guard !c.isEmpty else { return }
        let h = c["host"] as? String ?? "", p = c["port"] as? Int ?? 8765, tk = c["token"] as? String ?? ""
        let changed = h != host || p != port || tk != token
        host = h; port = p; token = tk
        shortcuts = c["shortcuts"] as? [String] ?? []
        if let pr = c["presets"] as? [String], !pr.isEmpty { presets = pr }
        if changed { connectDirect() }
    }

    func session(_ s: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {
        DispatchQueue.main.async { self.applyContext(s.receivedApplicationContext); self.updateMode() }
    }

    func session(_ s: WCSession, didReceiveApplicationContext c: [String: Any]) {
        DispatchQueue.main.async { self.applyContext(c) }
    }

    func sessionReachabilityDidChange(_ s: WCSession) {
        DispatchQueue.main.async { self.updateMode() }
    }

    func session(_ s: WCSession, didReceiveMessage m: [String: Any]) {
        DispatchQueue.main.async {
            switch m["t"] as? String {
            case "claude.update":
                self.claudeText = m["text"] as? String ?? ""
                if m["done"] as? Bool == true { self.claudeBusy = false; WKInterfaceDevice.current().play(.success) }
            case "phone.ack":
                WKInterfaceDevice.current().play(.success)
            default: break
            }
        }
    }
}
