//! Mouse movement simulation with Bézier curves and Perlin noise.

use crate::persona::MouseParams;

/// A 2D point coordinate.
#[derive(Debug, Clone, Copy)]
pub struct Point {
    /// X coordinate.
    pub x: f64,
    /// Y coordinate.
    pub y: f64,
}

/// A movement segment with timing (ms from start).
#[derive(Debug, Clone)]
pub struct MovementStep {
    /// X position.
    pub x: f64,
    /// Y position.
    pub y: f64,
    /// Milliseconds from start of movement.
    pub timestamp_ms: f64,
}

/// Human-like mouse movement simulator using Bézier curves.
pub struct MouseHumanizer {
    params: MouseParams,
}

impl MouseHumanizer {
    /// Create a new mouse humanizer with the given parameters.
    #[must_use]
    pub fn new(params: &MouseParams) -> Self {
        Self { params: *params }
    }

    /// Generate a movement path from `from` to `to`.
    ///
    /// Uses a cubic Bézier curve with Perlin noise jitter and an
    /// ease-in-out velocity profile. Returns steps sampled at ~10ms intervals.
    #[must_use]
    pub fn generate_path(&self, from: Point, to: Point, seed: u64) -> Vec<MovementStep> {
        let noise = PerlinNoise::new(seed);
        let (dx, dy) = (to.x - from.x, to.y - from.y);
        let dist = dx.hypot(dy);
        if dist < 1.0 {
            return vec![MovementStep {
                x: to.x,
                y: to.y,
                timestamp_ms: 0.0,
            }];
        }
        let dur_ms = (dist / self.params.speed) * 1000.0;
        let steps = (dur_ms / 10.0).ceil() as usize;
        let dt = dur_ms / steps as f64;
        let cp1 = control_point(from, to, self.params.curve, seed);
        let cp2 = control_point(from, to, self.params.curve, seed.wrapping_add(1));
        let mut out = Vec::with_capacity(steps);
        for i in 0..steps {
            let t = i as f64 / steps as f64;
            let et = ease_in_out_cubic(t);
            let (bx, by) = cubic_bezier(from, cp1, cp2, to, et);
            out.push(MovementStep {
                x: bx + noise.sample(t, self.params.tremor),
                y: by + noise.sample(t + 0.5, self.params.tremor),
                timestamp_ms: i as f64 * dt,
            });
        }
        out.push(MovementStep {
            x: to.x,
            y: to.y,
            timestamp_ms: dur_ms,
        });
        out
    }
}

fn ease_in_out_cubic(t: f64) -> f64 {
    if t < 0.5 {
        4.0 * t * t * t
    } else {
        1.0 - (-2.0 * t + 2.0).powi(3) / 2.0
    }
}

fn cubic_bezier(p0: Point, p1: Point, p2: Point, p3: Point, t: f64) -> (f64, f64) {
    let u = 1.0 - t;
    (
        u * u * u * p0.x + 3.0 * u * u * t * p1.x + 3.0 * u * t * t * p2.x + t * t * t * p3.x,
        u * u * u * p0.y + 3.0 * u * u * t * p1.y + 3.0 * u * t * t * p2.y + t * t * t * p3.y,
    )
}

fn control_point(from: Point, to: Point, curve: f64, seed: u64) -> Point {
    let (dx, dy) = (to.x - from.x, to.y - from.y);
    let dist = dx.hypot(dy);
    let pd = curve * dist * 0.3;
    let (nx, ny) = (-dy / dist, dx / dist);
    let h = seed.wrapping_mul(6_364_136_223_846_793_005) as f64 / u64::MAX as f64;
    let s = if h > 0.5 { 1.0 } else { -1.0 };
    Point {
        x: from.x + dx * 0.3 + nx * pd * s,
        y: from.y + dy * 0.3 + ny * pd * s,
    }
}

struct PerlinNoise {
    seed: u64,
}
impl PerlinNoise {
    fn new(seed: u64) -> Self {
        Self { seed }
    }
    fn sample(&self, t: f64, amp: f64) -> f64 {
        let h = self.seed.wrapping_add((t * 65536.0) as u64);
        let h = h.wrapping_mul(6_364_136_223_846_793_005) ^ (h >> 32);
        (h as f64 / u64::MAX as f64) * 2.0 * amp - amp
    }
}

#[cfg(test)]
mod tests {
    use super::{MouseHumanizer, MouseParams, MovementStep, Point};
    #[test]
    fn test_path_has_steps() {
        let h = MouseHumanizer::new(&MouseParams {
            speed: 500.0,
            curve: 0.5,
            tremor: 0.8,
        });
        assert!(
            h.generate_path(Point { x: 0., y: 0. }, Point { x: 800., y: 600. }, 42)
                .len()
                > 3
        );
    }
    #[test]
    fn test_path_ends_at_target() {
        let h = MouseHumanizer::new(&MouseParams {
            speed: 300.0,
            curve: 0.5,
            tremor: 0.5,
        });
        let p = h.generate_path(Point { x: 100., y: 200. }, Point { x: 500., y: 400. }, 7);
        let l = p.last().unwrap();
        assert!((l.x - 500.).abs() < 1.0);
        assert!((l.y - 400.).abs() < 1.0);
    }
    #[test]
    fn test_seeds_differ() {
        let h = MouseHumanizer::new(&MouseParams {
            speed: 500.,
            curve: 0.5,
            tremor: 0.8,
        });
        let key = |seed| {
            h.generate_path(Point { x: 0., y: 0. }, Point { x: 800., y: 600. }, seed)
                .iter()
                .take(5)
                .map(|s| format!("{:.0},{:.0}", s.x, s.y))
                .collect::<String>()
        };
        assert_ne!(key(1), key(2));
    }
    #[test]
    fn test_acceleration_non_linear() {
        let h = MouseHumanizer::new(&MouseParams {
            speed: 300.,
            curve: 0.,
            tremor: 0.,
        });
        let p = h.generate_path(Point { x: 0., y: 0. }, Point { x: 1000., y: 0. }, 0);
        let d: Vec<f64> = (1..p.len()).map(|i| p[i].x - p[i - 1].x).collect();
        let mid = d.len() / 2;
        let fa = d[..mid / 2].iter().sum::<f64>() / (mid / 2).max(1) as f64;
        let ma = d[mid / 2..mid / 2 + mid].iter().sum::<f64>() / mid.max(1) as f64;
        assert!(ma > fa, "mid velocity {ma} should exceed initial {fa}");
    }
}
