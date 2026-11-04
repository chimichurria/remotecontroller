import SwiftUI
import WatchKit

@main
struct RemoteHubWatchApp: App {
    var body: some Scene {
        WindowGroup { WatchRoot() }
    }
}

struct WatchRoot: View {
    @StateObject private var link = WatchLink.shared

    var body: some View {
        TabView {
            SlidesPage()
            MousePage()
            MediaPage()
            ClaudePage()
            PhonePage()
        }
        .tabViewStyle(.verticalPage)
        .environmentObject(link)
        .onAppear { link.start() }
        .overlay(alignment: .topTrailing) {
            Text(link.mode).font(.system(size: 9)).foregroundStyle(.secondary).padding(.trailing, 6)
        }
    }
}

/// Doble toque (Series 9+/Ultra 2, watchOS 11) = acción principal de la pantalla.
struct DoubleTap: ViewModifier {
    @ViewBuilder func body(content: Content) -> some View {
        if #available(watchOS 11.0, *) { content.handGestureShortcut(.primaryAction) } else { content }
    }
}

private func tick() { WKInterfaceDevice.current().play(.click) }

// MARK: Slides

struct SlidesPage: View {
    @EnvironmentObject var link: WatchLink
    @State private var crown = 0.0
    @State private var flick = false
    private let motion = MotionService()

    var body: some View {
        VStack(spacing: 6) {
            Button {
                link.send(["t": "slides", "action": "next"]); tick()
            } label: {
                Label("Siguiente", systemImage: "chevron.right.circle.fill")
                    .frame(maxWidth: .infinity, minHeight: 56)
            }
            .buttonStyle(.borderedProminent).modifier(DoubleTap())

            HStack {
                Button { link.send(["t": "slides", "action": "prev"]); tick() } label: { Image(systemName: "chevron.left") }
                Button { link.send(["t": "slides", "action": "start"]); tick() } label: { Image(systemName: "play.fill") }
                Button { link.send(["t": "slides", "action": "end"]); tick() } label: { Image(systemName: "xmark") }
            }
            Toggle("Flick", isOn: $flick).font(.footnote)
        }
        .focusable()
        .digitalCrownRotation($crown, from: -10_000, through: 10_000, by: 1, sensitivity: .low,
                              isContinuous: true, isHapticFeedbackEnabled: true)
        .onChange(of: crown) { old, new in
            link.send(["t": "slides", "action": new > old ? "next" : "prev"])
        }
        .onChange(of: flick) { _, on in
            if on {
                motion.startFlick(invert: false) { dir in
                    link.send(["t": "slides", "action": dir > 0 ? "next" : "prev"])
                    WKInterfaceDevice.current().play(.directionUp)
                }
            } else { motion.stop() }
        }
        .onDisappear { motion.stop(); flick = false }
    }
}

// MARK: Mouse aéreo

struct MousePage: View {
    @EnvironmentObject var link: WatchLink
    @State private var air = false
    @State private var invertX = false
    @State private var invertY = false
    @State private var crown = 0.0
    private let motion = MotionService()

    var body: some View {
        ScrollView {
            VStack(spacing: 6) {
                Toggle("Mouse aéreo", isOn: $air)
                Button { link.send(["t": "mouse.click", "button": "left", "count": 1]); tick() } label: {
                    Label("Click", systemImage: "cursorarrow.click").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent).modifier(DoubleTap())
                HStack {
                    Button { link.send(["t": "mouse.click", "button": "right", "count": 1]); tick() } label: { Text("Der.") }
                    Button { link.send(["t": "mouse.click", "button": "left", "count": 2]); tick() } label: { Text("Doble") }
                }
                Text("Corona = scroll").font(.footnote).foregroundStyle(.secondary)
                Toggle("Invertir ←→", isOn: $invertX).font(.footnote)
                Toggle("Invertir ↑↓", isOn: $invertY).font(.footnote)
            }
        }
        .focusable()
        .digitalCrownRotation($crown, from: -100_000, through: 100_000, by: 1, sensitivity: .medium,
                              isContinuous: true, isHapticFeedbackEnabled: false)
        .onChange(of: crown) { old, new in link.send(["t": "mouse.scroll", "dx": 0, "dy": (new - old) * 0.5]) }
        .onChange(of: air) { _, _ in restart() }
        .onChange(of: invertX) { _, _ in restart() }
        .onChange(of: invertY) { _, _ in restart() }
        .onDisappear { motion.stop(); air = false }
    }

    private func restart() {
        motion.stop()
        guard air else { return }
        motion.startAir(sensitivity: 1.0, invertX: invertX, invertY: invertY) { dx, dy in
            link.send(["t": "mouse.move", "dx": dx, "dy": dy])
        }
    }
}

// MARK: Multimedia

struct MediaPage: View {
    @EnvironmentObject var link: WatchLink
    @State private var crown = 0.0

    var body: some View {
        VStack(spacing: 8) {
            Button { link.send(["t": "media", "action": "play_pause"]); tick() } label: {
                Image(systemName: "playpause.fill").font(.title2).frame(maxWidth: .infinity, minHeight: 50)
            }
            .buttonStyle(.borderedProminent).modifier(DoubleTap())
            HStack {
                Button { link.send(["t": "media", "action": "prev"]); tick() } label: { Image(systemName: "backward.fill") }
                Button { link.send(["t": "media", "action": "next"]); tick() } label: { Image(systemName: "forward.fill") }
            }
            Text("Corona = volumen").font(.footnote).foregroundStyle(.secondary)
        }
        .focusable()
        .digitalCrownRotation($crown, from: -10_000, through: 10_000, by: 1, sensitivity: .low,
                              isContinuous: true, isHapticFeedbackEnabled: true)
        .onChange(of: crown) { old, new in
            link.send(["t": "media", "action": new > old ? "vol_up" : "vol_down"])
        }
    }
}

// MARK: Claude Code

struct ClaudePage: View {
    @EnvironmentObject var link: WatchLink
    @State private var prompt = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                // En el Watch, tocar el campo abre dictado/garabato.
                TextField("Dictar pedido", text: $prompt)
                    .onSubmit { if !prompt.isEmpty { link.claude(text: prompt); prompt = "" } }
                ForEach(link.presets, id: \.self) { p in
                    Button(p) { link.claudePreset(p); tick() }.disabled(link.claudeBusy)
                }
                if link.claudeBusy {
                    HStack { ProgressView(); Button("Cancelar") { link.send(["t": "claude.cancel"]) } }
                }
                if !link.claudeText.isEmpty {
                    Text(link.claudeText).font(.footnote)
                }
            }
        }
    }
}

// MARK: iPhone

struct PhonePage: View {
    @EnvironmentObject var link: WatchLink

    var body: some View {
        ScrollView {
            VStack(spacing: 6) {
                Button { link.sendPhone("camera.shutter"); tick() } label: {
                    Label("Foto", systemImage: "camera.fill").frame(maxWidth: .infinity, minHeight: 44)
                }
                .buttonStyle(.borderedProminent).modifier(DoubleTap())
                Button { link.sendPhone("torch"); tick() } label: {
                    Label("Linterna", systemImage: "flashlight.on.fill").frame(maxWidth: .infinity)
                }
                ForEach(link.shortcuts, id: \.self) { s in
                    Button(s) { link.sendPhone("shortcut.run", name: s); tick() }
                }
                Text("La app del iPhone tiene que estar abierta.").font(.system(size: 10)).foregroundStyle(.secondary)
            }
        }
    }
}
