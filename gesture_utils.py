"""Shared static-hand comparison. No rotation or handedness correction."""
import math

class LandmarkError(ValueError):
    pass

def validate(points):
    if not isinstance(points, list) or len(points) != 21:
        raise LandmarkError('Expected 21 landmarks in order 0-20.')
    result = []
    for i, p in enumerate(points):
        if not isinstance(p, dict) or p.get('id', i) != i:
            raise LandmarkError('Landmark IDs must be in order 0-20.')
        values = []
        for key in ('x', 'y', 'z'):
            value = p.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise LandmarkError('Landmarks must contain finite numeric x/y/z values.')
            values.append(value)
        result.append(values)
    return result

def normalize(points, scale=True):
    values = validate(points)
    wrist = values[0]
    centered = [[v-w for v, w in zip(p, wrist)] for p in values]
    # Middle-finger MCP, landmark 9. Units are the existing MediaPipe image coordinates.
    palm = math.sqrt(sum(v*v for v in centered[9]))
    if scale and palm < 1e-6:
        raise LandmarkError('Palm measurement is too small to normalize. Show your whole hand and recapture.')
    divisor = palm if scale else 1.0
    return [dict(id=i, x=p[0]/divisor, y=p[1]/divisor, z=p[2]/divisor) for i, p in enumerate(centered)]

def compare(user, reference, method='original', slope=None, threshold=70):
    if method not in ('original', 'normalized', 'angles'):
        raise LandmarkError('Method must be original, normalized, or angles.')
    slope = (300 if method == 'original' else 1 if method == 'angles' else 30) if slope is None else slope
    if isinstance(slope, bool) or not isinstance(slope, (int, float)) or not math.isfinite(slope) or slope <= 0:
        raise LandmarkError('Slope must be a positive finite number.')
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 <= threshold <= 100:
        raise LandmarkError('Threshold must be between 0 and 100.')
    if method == 'angles':
        u = joint_angles(user)
        r = reference['angles'] if isinstance(reference, dict) and 'angles' in reference else joint_angles(reference)
        if len(r) != 10 or any(not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 180 for v in r):
            raise LandmarkError('Expected ten valid joint angles.')
        # Use the largest finger discrepancy so one straight finger is not diluted by four matching fingers.
        finger_errors = [sum(abs(u[j]-r[j]) for j in (i,i+1))/2 for i in range(0,10,2)]
        distance = max(finger_errors)
        score = round(max(0,100-slope*distance))
        return dict(method=method,distance=distance,score=score,passed=score>=threshold,slope=slope,threshold=threshold,
                    finger_errors=dict(zip(('thumb','index','middle','ring','little'),finger_errors)))
    u, r = normalize(user, method == 'normalized'), normalize(reference, method == 'normalized')
    distance = sum(math.sqrt(sum((a[k]-b[k])**2 for k in ('x','y','z'))) for a,b in zip(u,r))/21
    score = round(max(0, 100-slope*distance))
    return dict(method=method, distance=distance, score=score, passed=score >= threshold, slope=slope, threshold=threshold)

def average(samples, method='original'):
    if method == 'angles':
        if len(samples) != 5:
            raise LandmarkError('Exactly five reference captures are required.')
        features = [joint_angles(p) for p in samples]
        return {'angles':[sum(f[i] for f in features)/5 for i in range(10)], 'reference_method':'mean_joint_angles'}
    aligned = [normalize(p, method == 'normalized') for p in samples]
    if len(aligned) != 5:
        raise LandmarkError('Exactly five reference captures are required.')
    return [dict(id=i, **{k:sum(p[i][k] for p in aligned)/5 for k in ('x','y','z')}) for i in range(21)]


def joint_angles(points):
    """Ten 3D bend angles in existing image-landmark units; not world-coordinate angles.
    Straight joints are near 180 degrees. No handedness correction or thumb-position feature.
    """
    values = validate(points)
    triples = [(1,2,3),(2,3,4),(5,6,7),(6,7,8),(9,10,11),(10,11,12),
               (13,14,15),(14,15,16),(17,18,19),(18,19,20)]
    result=[]
    for a,b,c in triples:
        u=[values[a][k]-values[b][k] for k in range(3)]
        v=[values[c][k]-values[b][k] for k in range(3)]
        nu=math.sqrt(sum(x*x for x in u));nv=math.sqrt(sum(x*x for x in v))
        if nu<1e-8 or nv<1e-8:
            raise LandmarkError('Finger segment is too small to measure. Show your whole hand and recapture.')
        cosine=sum(x*y for x,y in zip(u,v))/(nu*nv)
        result.append(math.degrees(math.acos(max(-1,min(1,cosine)))))
    return result


# ── PHASE 3: MOVING-SIGN COMPARISON (DTW) ──
# A moving sign is a short sequence of frames instead of one snapshot. Speed
# varies between attempts (someone might sign faster or slower), so frame N
# of a test clip rarely lines up with frame N of the reference. Dynamic Time
# Warping (DTW) finds the best alignment between two sequences of different
# lengths before measuring how different they are, so it tolerates speed
# variation without tolerating a genuinely different movement.

def _sequence_features(frames, method):
    """Turn a list of 21-landmark frames into a list of per-frame feature
    vectors. 'angles' (the static-sign default) is also the default here,
    reusing the same joint-angle feature -- no separate calibration needed."""
    if not isinstance(frames, list) or not frames:
        raise LandmarkError('Sequence must be a non-empty list of frames.')
    if method == 'angles':
        return [joint_angles(f) for f in frames]
    if method == 'normalized':
        return [[v for p in normalize(f, True) for v in (p['x'], p['y'], p['z'])] for f in frames]
    raise LandmarkError('Method must be angles or normalized for sequence comparison.')

def _euclidean(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

def dtw_distance(seq_a, seq_b):
    """Classic O(n*m) dynamic-time-warping distance between two equal-width
    feature sequences. Normalized by path length so sequences of different
    lengths (different signing speeds) stay comparable."""
    n, m = len(seq_a), len(seq_b)
    if n == 0 or m == 0:
        raise LandmarkError('Sequence must have at least one frame.')
    INF = float('inf')
    cost = [[INF] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d = _euclidean(seq_a[i - 1], seq_b[j - 1])
            cost[i][j] = d + min(cost[i - 1][j], cost[i][j - 1], cost[i - 1][j - 1])
    return cost[n][m] / (n + m)

def compare_sequence(user_frames, reference_frames, method='angles', slope=None, threshold=50):
    """Score a moving sign against a reference recording. Separate from
    compare() (static signs) and not called anywhere in the live lesson
    flow yet -- Phase 3 prototype only, reached through its own experimental
    endpoint so it can't affect /api/analyze."""
    if method not in ('angles', 'normalized'):
        raise LandmarkError('Method must be angles or normalized for sequence comparison.')
    slope = (2 if method == 'angles' else 20) if slope is None else slope
    if isinstance(slope, bool) or not isinstance(slope, (int, float)) or not math.isfinite(slope) or slope <= 0:
        raise LandmarkError('Slope must be a positive finite number.')
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 <= threshold <= 100:
        raise LandmarkError('Threshold must be between 0 and 100.')
    user_feats = _sequence_features(user_frames, method)
    ref_feats = _sequence_features(reference_frames, method)
    distance = dtw_distance(user_feats, ref_feats)
    score = round(max(0, 100 - slope * distance))
    return dict(method=method, distance=distance, score=score, passed=score >= threshold,
                slope=slope, threshold=threshold,
                user_frames=len(user_frames), reference_frames=len(reference_frames))
