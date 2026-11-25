"""Load explicit per-lesson static recognition settings without changing the database."""
import json
import math
from pathlib import Path
from gesture_utils import compare, apply_shape_checks, normalize, LandmarkError

PROFILE_PATH = Path(__file__).resolve().parent / 'recognition' / 'static_profiles.json'

def apply_number_7_checks(points, comparison, settings):
    # Reduce the ring angle's influence, while checking thumb–ring proximity.
    weight = settings["ring_weight"]
    limit = settings["thumb_ring_gap_limit"]

    if not 0 < weight <= 1 or not limit > 0:
        raise LandmarkError("Invalid number 7 recognition settings.")

    errors = dict(comparison["finger_errors"])
    errors["ring"] *= weight
    distance = max(errors.values())

    angle_score = round(max(
        0, 100 - comparison["slope"] * distance
    ))

    points = normalize(points)
    gap = math.sqrt(sum(
        (points[4][axis] - points[16][axis]) ** 2
        for axis in ("x", "y", "z")
    ))

    threshold = comparison["threshold"]
    proximity_passed = gap <= limit
    shape_score = math.floor(max(
        0, 100 - (100 - threshold) * gap / limit
    ))

    result = dict(comparison)
    result.update(
        unweighted_angle_score=comparison["score"],
        distance=distance,
        weighted_finger_errors=errors,
        angle_score=angle_score,
        shape_score=shape_score,
        shape_features={"thumb_ring_tip_gap": gap},
        shape_upper_limits={"thumb_ring_tip_gap": limit},
        shape_checks={"thumb_ring_tip_gap": proximity_passed},
        ring_weight=weight,
        score=min(angle_score, shape_score),
    )
    result["passed"] = (
        proximity_passed and result["score"] >= threshold
    )
    return result

def compare_lesson(user_landmarks, reference_data, lesson_id, sign_name, request_data):
    # This file is required so a missing installation cannot silently use old scoring.
    with PROFILE_PATH.open(encoding='utf-8') as source:
        document = json.load(source)
    if document.get('schema_version') != 1 or not isinstance(document.get('lessons'), dict):
        raise LandmarkError('Invalid static recognition settings file.')
    profile = document['lessons'].get(str(lesson_id))
    if profile and profile.get('enabled') is True:
        if profile.get('sign_name') != sign_name:
            raise LandmarkError('Lesson name does not match its recognition profile. Check the lesson ID.')
        if profile.get('method') != 'angles':
            raise LandmarkError('This pilot requires an angles profile.')
        angles = profile.get('reference', {}).get('angles')
        if (not isinstance(angles, list) or len(angles) != 10
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) or not 0 <= v <= 180 for v in angles)):
            raise LandmarkError('The recognition profile must contain ten finite joint angles.')
        # Configured lessons use server-owned settings, even if an old browser sends "original".
        result = compare(user_landmarks, {'angles': angles}, 'angles',
                         profile['slope'], profile['threshold'])
        number_7 = profile.get("number_7_checks", {})
        if number_7.get("enabled") is True:
            if sign_name != "7":
                raise LandmarkError("Number 7 checks require sign name 7.")
            result = apply_number_7_checks(
                user_landmarks, result, number_7
            )
        if profile.get('shape_checks', {}).get('enabled') is True:
            result = apply_shape_checks(user_landmarks, result, profile['shape_checks'])
        result.update(reference_source=('configured_single_angles'
                                        if profile['reference'].get('reference_method') == 'single_capture_joint_angles'
                                        else 'configured_average_angles'),
                      reference_hand=profile.get('reference_hand'),
                      reference_capture_count=profile.get('capture_count'),
                      recognition_scope=profile.get('evaluation_scope'))
        return result
    method = request_data.get('method', 'original')
    slope = request_data.get('slope', {'original': 300, 'normalized': 30, 'angles': 1}.get(method, 300))
    result = compare(user_landmarks, reference_data['landmarks'], method,
                     slope, request_data.get('threshold', 70))
    result['reference_source'] = 'database_landmarks'
    return result
