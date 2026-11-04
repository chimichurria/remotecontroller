import CoreMotion
import Foundation

/// Giroscopio del Watch: "mouse aéreo" (apuntar con la muñeca) y "flick" (giro de muñeca).
final class MotionService {
    private let mgr = CMMotionManager()
    private var lastFlick = Date.distantPast

    /// Mouse aéreo. yaw = giro sobre la vertical (horizontal en pantalla),
    /// pitch = giro sobre el eje perpendicular al antebrazo (vertical).
    /// Independiente de en qué muñeca lo uses; si un eje queda al revés, usá los switches de invertir.
    func startAir(sensitivity: Double, invertX: Bool, invertY: Bool, handler: @escaping (Double, Double) -> Void) {
        guard mgr.isDeviceMotionAvailable else { return }
        mgr.deviceMotionUpdateInterval = 1.0 / 30.0
        mgr.startDeviceMotionUpdates(to: .main) { dm, _ in
            guard let dm else { return }
            let g = dm.gravity, r = dm.rotationRate
            let yaw = r.x * g.x + r.y * g.y + r.z * g.z
            // eje de pitch = (eje Y del reloj, hacia los dedos) × gravedad = (g.z, 0, -g.x)
            let n = max(0.0001, (g.z * g.z + g.x * g.x).squareRoot())
            let pitch = r.x * (g.z / n) + r.z * (-g.x / n)
            let k = 20.0 * sensitivity
            handler((invertX ? 1 : -1) * yaw * k, (invertY ? 1 : -1) * pitch * k)
        }
    }

    /// Flick: giro rápido del antebrazo. +1 = un sentido, -1 = el otro.
    func startFlick(threshold: Double = 5.0, invert: Bool, handler: @escaping (Int) -> Void) {
        guard mgr.isDeviceMotionAvailable else { return }
        mgr.deviceMotionUpdateInterval = 1.0 / 50.0
        mgr.startDeviceMotionUpdates(to: .main) { [weak self] dm, _ in
            guard let self, let dm else { return }
            let w = dm.rotationRate.y
            guard abs(w) > threshold, Date().timeIntervalSince(self.lastFlick) > 0.8 else { return }
            self.lastFlick = Date()
            handler((w > 0) != invert ? 1 : -1)
        }
    }

    func stop() { mgr.stopDeviceMotionUpdates() }
}
