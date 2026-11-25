"""Tests for the moving-sign (DTW) comparison. Run: python -m unittest test_dtw_sequences -v"""
import unittest, math
import gesture_utils as g

def hand(openness, mirror=False):
    """Synthetic hand, openness 0 = fist ... 1 = fully open. Wrist at the origin and the
    middle-finger MCP (landmark 9) at distance 1, so palm length is exactly 1."""
    sign = -1 if mirror else 1
    columns = {1: -0.5, 5: -0.3, 9: 0.0, 13: 0.3, 17: 0.55}      # first landmark id of each finger -> x
    start_y = {1: 0.3, 5: 1.0, 9: 1.0, 13: 1.0, 17: 0.9}         # y of its first joint
    reach = 0.15 + 0.85 * openness                                # how far the finger extends
    pts = [dict(id=0, x=0.0, y=0.0, z=0.0)] + [None] * 20
    for first, x in columns.items():
        for k in range(4):
            y = start_y[first] if k == 0 else start_y[first] + reach * 0.45 * k
            pts[first + k] = dict(id=first + k, x=sign * x, y=y, z=0.0)
    return pts

def open_motion(n=8):
    return [hand(i / (n - 1)) for i in range(n)]

def hold_then_open(hold=4, n=8):
    return [hand(0.0)] * hold + [hand(i / (n - 1)) for i in range(n)]

class FingertipFeatures(unittest.TestCase):
    def test_five_values_and_open_larger_than_closed(self):
        closed, opened = g.fingertip_distances(hand(0.0)), g.fingertip_distances(hand(1.0))
        self.assertEqual(len(closed), 5)
        self.assertTrue(all(o > c for o, c in zip(opened, closed)))

    def test_scale_invariant(self):
        base = hand(0.7)
        big = [dict(id=p['id'], x=p['x'] * 3, y=p['y'] * 3, z=p['z'] * 3) for p in base]
        for a, b in zip(g.fingertip_distances(base), g.fingertip_distances(big)):
            self.assertAlmostEqual(a, b, places=6)

    def test_left_right_mirror_gives_same_features(self):
        for a, b in zip(g.fingertip_distances(hand(0.5)), g.fingertip_distances(hand(0.5, mirror=True))):
            self.assertAlmostEqual(a, b, places=6)

    def test_rejects_tiny_palm(self):
        flat = [dict(id=i, x=0.0, y=0.0, z=0.0) for i in range(21)]
        with self.assertRaises(g.LandmarkError):
            g.fingertip_distances(flat)

    def test_rejects_wrong_landmark_count(self):
        with self.assertRaises(g.LandmarkError):
            g.fingertip_distances(hand(0.5)[:20])

class SequenceComparison(unittest.TestCase):
    def test_identical_sequence_scores_100(self):
        ref = open_motion()
        r = g.compare_sequence(ref, ref, method='fingertips')
        self.assertAlmostEqual(r['distance'], 0.0, places=9)
        self.assertEqual(r['score'], 100)

    def test_speed_change_still_scores_high(self):
        ref = open_motion(8)
        slow = open_motion(14)
        r = g.compare_sequence(slow, ref, method='fingertips')
        self.assertGreater(r['score'], 80)

    def test_holding_start_pose_is_tolerated(self):
        r = g.compare_sequence(hold_then_open(), open_motion(), method='fingertips')
        self.assertGreater(r['score'], 80)

    def test_reverse_motion_scores_much_lower_than_correct(self):
        ref = open_motion()
        correct = g.compare_sequence(open_motion(11), ref, method='fingertips')['score']
        reverse = g.compare_sequence(list(reversed(open_motion(11))), ref, method='fingertips')['score']
        self.assertGreater(correct - reverse, 40)

    def test_holding_still_scores_much_lower_than_correct(self):
        ref = open_motion()
        correct = g.compare_sequence(open_motion(11), ref, method='fingertips')['score']
        still = g.compare_sequence([hand(0.0)] * 10, ref, method='fingertips')['score']
        self.assertGreater(correct - still, 30)

    def test_default_slopes_per_method(self):
        ref = open_motion()
        self.assertEqual(g.compare_sequence(ref, ref, method='fingertips')['slope'], 100)
        self.assertEqual(g.compare_sequence(ref, ref, method='angles')['slope'], 2)

    def test_unknown_method_and_bad_inputs(self):
        ref = open_motion()
        with self.assertRaises(g.LandmarkError): g.compare_sequence(ref, ref, method='nope')
        with self.assertRaises(g.LandmarkError): g.compare_sequence([], ref, method='fingertips')
        with self.assertRaises(g.LandmarkError): g.compare_sequence(ref, ref, method='fingertips', slope=0)
        with self.assertRaises(g.LandmarkError): g.compare_sequence(ref, ref, method='fingertips', threshold=101)

if __name__ == '__main__':
    unittest.main()
