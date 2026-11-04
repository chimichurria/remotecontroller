import SwiftUI
import UIKit

/// Superficie táctil: 1 dedo = mover, 2 dedos = scroll, tap = click,
/// tap con 2 dedos = click derecho, mantener y arrastrar = arrastrar.
struct TrackpadSurface: UIViewRepresentable {
    var onMove: (CGFloat, CGFloat) -> Void
    var onScroll: (CGFloat, CGFloat) -> Void
    var onClick: (String) -> Void
    var onDrag: (Bool) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> UIView {
        let v = UIView()
        v.backgroundColor = .clear
        v.isMultipleTouchEnabled = true
        let c = context.coordinator

        let pan1 = UIPanGestureRecognizer(target: c, action: #selector(Coordinator.pan1(_:)))
        pan1.minimumNumberOfTouches = 1; pan1.maximumNumberOfTouches = 1
        let pan2 = UIPanGestureRecognizer(target: c, action: #selector(Coordinator.pan2(_:)))
        pan2.minimumNumberOfTouches = 2; pan2.maximumNumberOfTouches = 2
        let tap = UITapGestureRecognizer(target: c, action: #selector(Coordinator.tap))
        let tap2 = UITapGestureRecognizer(target: c, action: #selector(Coordinator.tap2))
        tap2.numberOfTouchesRequired = 2
        let press = UILongPressGestureRecognizer(target: c, action: #selector(Coordinator.press(_:)))
        press.minimumPressDuration = 0.45
        press.allowableMovement = 10_000
        press.delegate = c
        pan1.delegate = c

        [pan1, pan2, tap, tap2, press].forEach(v.addGestureRecognizer)
        return v
    }

    func updateUIView(_ uiView: UIView, context: Context) { context.coordinator.parent = self }

    final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        var parent: TrackpadSurface
        private var dragging = false
        private var lastPress: CGPoint = .zero
        private let haptic = UIImpactFeedbackGenerator(style: .light)

        init(_ p: TrackpadSurface) { parent = p }

        @objc func pan1(_ g: UIPanGestureRecognizer) {
            guard !dragging else { return }
            let t = g.translation(in: g.view)
            g.setTranslation(.zero, in: g.view)
            parent.onMove(t.x, t.y)
        }

        @objc func pan2(_ g: UIPanGestureRecognizer) {
            let t = g.translation(in: g.view)
            g.setTranslation(.zero, in: g.view)
            // Scroll "natural": arrastrar hacia arriba sube el contenido.
            parent.onScroll(t.x * 0.1, -t.y * 0.1)
        }

        @objc func tap() { haptic.impactOccurred(); parent.onClick("left") }
        @objc func tap2() { haptic.impactOccurred(); parent.onClick("right") }

        @objc func press(_ g: UILongPressGestureRecognizer) {
            let p = g.location(in: g.view)
            switch g.state {
            case .began:
                dragging = true
                lastPress = p
                UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                parent.onDrag(true)
            case .changed:
                parent.onMove(p.x - lastPress.x, p.y - lastPress.y)
                lastPress = p
            case .ended, .cancelled, .failed:
                if dragging { dragging = false; parent.onDrag(false) }
            default: break
            }
        }

        func gestureRecognizer(_ a: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith b: UIGestureRecognizer) -> Bool {
            (a is UILongPressGestureRecognizer && b is UIPanGestureRecognizer) ||
            (a is UIPanGestureRecognizer && b is UILongPressGestureRecognizer)
        }
    }
}

struct TrackpadView: View {
    @EnvironmentObject var hub: Hub

    var body: some View {
        VStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 24)
                    .fill(LinearGradient(colors: [.gray.opacity(0.25), .gray.opacity(0.1)],
                                         startPoint: .top, endPoint: .bottom))
                TrackpadSurface(
                    onMove: { hub.send(["t": "mouse.move", "dx": $0, "dy": $1]) },
                    onScroll: { hub.send(["t": "mouse.scroll", "dx": $0, "dy": $1]) },
                    onClick: { hub.send(["t": "mouse.click", "button": $0, "count": 1]) },
                    onDrag: { hub.send(["t": $0 ? "mouse.down" : "mouse.up", "button": "left"]) }
                )
                .clipShape(RoundedRectangle(cornerRadius: 24))
                Text("1 dedo mueve · 2 dedos scroll · tap click\n2 dedos tap = derecho · mantené = arrastrar")
                    .font(.footnote).multilineTextAlignment(.center)
                    .foregroundStyle(.secondary).allowsHitTesting(false)
                    .frame(maxHeight: .infinity, alignment: .bottom).padding(.bottom, 12)
            }
            HStack(spacing: 10) {
                pad("Click", "cursorarrow.click") { hub.send(["t": "mouse.click", "button": "left", "count": 1]) }
                pad("Doble", "cursorarrow.click.2") { hub.send(["t": "mouse.click", "button": "left", "count": 2]) }
                pad("Derecho", "contextualmenu.and.cursorarrow") { hub.send(["t": "mouse.click", "button": "right", "count": 1]) }
            }
        }
        .padding()
    }

    private func pad(_ title: String, _ icon: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: icon).frame(maxWidth: .infinity)
        }.buttonStyle(.bordered).controlSize(.large)
    }
}
