"""Pure-Python tests (no database). Run: python -m unittest buses.test_eta   (from /backend)"""
import unittest

from . import eta

# 101-vertex straight route heading north, ~33 m between vertices.
PATH = [[23.0 + k * 0.0003, 90.0] for k in range(101)]
SEG = eta.haversine(PATH[0], PATH[1])


class EtaTests(unittest.TestCase):
    def test_haversine_one_degree_latitude(self):
        self.assertAlmostEqual(eta.haversine([0, 0], [1, 0]), 111_195, delta=50)

    def test_nearest_index_snaps(self):
        self.assertEqual(eta.nearest_index(PATH, [23.0151, 90.00002]), 50)

    def test_passed_stop_returns_none(self):
        self.assertIsNone(eta.eta_from_indexes(PATH, 60, 40, [40], [20]))

    def test_distance_and_eta_without_dwell(self):
        r = eta.eta_from_indexes(PATH, 10, 40, [10, 40], [36.0])      # 36 km/h = 10 m/s
        self.assertAlmostEqual(r.distance_m, 30 * SEG, places=3)
        self.assertEqual(r.stops_between, 0)
        self.assertAlmostEqual(r.eta_seconds, 30 * SEG / 10.0, places=3)
        self.assertEqual(r.status, "Approaching")

    def test_dwell_counts_only_intermediate_stops(self):
        # stops at 10 (bus is here), 20, 30 (intermediate), 40 (target), 70 (beyond)
        r = eta.eta_from_indexes(PATH, 10, 40, [10, 20, 30, 40, 70], [36.0])
        self.assertEqual(r.stops_between, 2)
        self.assertAlmostEqual(r.eta_seconds, 30 * SEG / 10.0 + 40, places=3)

    def test_speed_floor(self):
        self.assertEqual(eta.ema_speed_ms([0, 0, 0]), eta.MIN_SPEED_MS)
        self.assertEqual(eta.ema_speed_ms([]), eta.MIN_SPEED_MS)
        r = eta.eta_from_indexes(PATH, 0, 10, [], [0.0])
        self.assertAlmostEqual(r.eta_seconds, 10 * SEG / 3.0, places=3)

    def test_ema_converts_kmh_and_weights_recent(self):
        self.assertAlmostEqual(eta.ema_speed_ms([36.0] * 5), 10.0, places=6)
        self.assertGreater(eta.ema_speed_ms([18] * 9 + [54]), eta.ema_speed_ms([54] + [18] * 9))

    def test_ema_uses_last_ten_only(self):
        self.assertAlmostEqual(eta.ema_speed_ms([0.0] * 50 + [36.0] * 10), 10.0, places=6)

    def test_at_stop_status_and_zero_eta(self):
        r = eta.eta_from_indexes(PATH, 40, 40, [40], [30.0])
        self.assertEqual((r.eta_seconds, r.distance_m, r.status), (0.0, 0.0, "At Stop"))


if __name__ == "__main__":
    unittest.main()
