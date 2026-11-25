"""Tests for the fingertip-contact check used by letters such as F. Run: python -m unittest test_tip_contact -v"""
import json
import tempfile
import unittest
from pathlib import Path

import gesture_utils as gu
import static_recognition as sr


def hand(tip_gap=0.0):
    """Synthetic hand, wrist at the origin and palm length exactly 1.
    The thumb tip (4) is placed tip_gap away from the index tip (8) along x."""
    columns = {1: -0.5, 5: -0.3, 9: 0.0, 13: 0.3, 17: 0.55}
    start_y = {1: 0.3, 5: 1.0, 9: 1.0, 13: 1.0, 17: 0.9}
    pts = [dict(id=0, x=0.0, y=0.0, z=0.0)] + [None] * 20
    for first, x in columns.items():
        for k in range(4):
            y = start_y[first] if k == 0 else start_y[first] + 0.2 * k
            pts[first + k] = dict(id=first + k, x=x, y=y, z=0.01 * k)
    pts[9] = dict(id=9, x=0.0, y=1.0, z=0.0)
    pts[4] = dict(id=4, x=pts[8]['x'] + tip_gap, y=pts[8]['y'], z=pts[8]['z'])
    return pts


def comparison(score=100, threshold=70):
    return dict(method='angles', score=score, threshold=threshold, slope=1, passed=score >= threshold)


SETTINGS = {'enabled': True, 'name': 'thumb_index_tip_gap', 'landmarks': [4, 8], 'upper_limit': 0.3}


class TipContactCheck(unittest.TestCase):
    def test_touching_tips_pass_with_full_shape_score(self):
        r = sr.apply_tip_contact_check(hand(0.0), comparison(), SETTINGS)
        self.assertAlmostEqual(r['shape_features']['thumb_index_tip_gap'], 0.0, places=6)
        self.assertEqual(r['shape_score'], 100)
        self.assertTrue(r['passed'])

    def test_gap_at_the_limit_passes_with_threshold_score(self):
        r = sr.apply_tip_contact_check(hand(0.3), comparison(), SETTINGS)
        self.assertEqual(r['shape_score'], 70)
        self.assertTrue(r['passed'])

    def test_gap_over_the_limit_fails_even_with_perfect_angles(self):
        r = sr.apply_tip_contact_check(hand(0.45), comparison(100), SETTINGS)
        self.assertFalse(r['shape_checks']['thumb_index_tip_gap'])
        self.assertFalse(r['passed'])
        self.assertLess(r['score'], 70)

    def test_final_score_is_the_lower_of_angle_and_shape_scores(self):
        r = sr.apply_tip_contact_check(hand(0.0), comparison(score=75), SETTINGS)
        self.assertEqual(r['score'], 75)
        r = sr.apply_tip_contact_check(hand(0.15), comparison(score=100), SETTINGS)
        self.assertEqual(r['score'], r['shape_score'])
        self.assertEqual(r['angle_score'], 100)

    def test_good_contact_cannot_rescue_bad_angles(self):
        r = sr.apply_tip_contact_check(hand(0.0), comparison(score=40), SETTINGS)
        self.assertFalse(r['passed'])

    def test_input_comparison_is_not_modified(self):
        c = comparison()
        sr.apply_tip_contact_check(hand(0.0), c, SETTINGS)
        self.assertNotIn('shape_score', c)

    def test_invalid_settings_are_rejected(self):
        bad = [
            dict(SETTINGS, landmarks=[4, 4]),
            dict(SETTINGS, landmarks=[4]),
            dict(SETTINGS, landmarks=[4, 21]),
            dict(SETTINGS, landmarks=[True, 8]),
            dict(SETTINGS, upper_limit=0),
            dict(SETTINGS, upper_limit=-1),
            dict(SETTINGS, upper_limit=True),
            dict(SETTINGS, upper_limit=float('nan')),
            {k: v for k, v in SETTINGS.items() if k != 'upper_limit'},
        ]
        for settings in bad:
            with self.subTest(settings=settings):
                with self.assertRaises(gu.LandmarkError):
                    sr.apply_tip_contact_check(hand(0.0), comparison(), settings)


class CompareLessonUsesTheCheck(unittest.TestCase):
    def setUp(self):
        self.original_path = sr.PROFILE_PATH
        self.tmp = tempfile.TemporaryDirectory()
        sr.PROFILE_PATH = Path(self.tmp.name) / 'static_profiles.json'

    def tearDown(self):
        sr.PROFILE_PATH = self.original_path
        self.tmp.cleanup()

    def write_profile(self, tip_contact):
        profile = {'enabled': True, 'sign_name': 'F', 'method': 'angles', 'slope': 1, 'threshold': 70,
                   'reference': {'angles': gu.joint_angles(hand(0.0)), 'reference_method': 'mean_joint_angles'}}
        if tip_contact is not None:
            profile['tip_contact_check'] = tip_contact
        sr.PROFILE_PATH.write_text(json.dumps({'schema_version': 1, 'lessons': {'23': profile}}), encoding='utf-8')

    def test_without_the_block_angles_alone_decide(self):
        self.write_profile(None)
        r = sr.compare_lesson(hand(0.5), None, 23, 'F', {})
        self.assertNotIn('shape_features', r)

    def test_with_the_block_a_gap_is_rejected(self):
        self.write_profile(SETTINGS)
        self.assertTrue(sr.compare_lesson(hand(0.0), None, 23, 'F', {})['passed'])
        self.assertFalse(sr.compare_lesson(hand(0.6), None, 23, 'F', {})['passed'])

    def test_a_disabled_block_is_ignored(self):
        self.write_profile(dict(SETTINGS, enabled=False))
        r = sr.compare_lesson(hand(0.6), None, 23, 'F', {})
        self.assertNotIn('shape_features', r)


if __name__ == '__main__':
    unittest.main()
