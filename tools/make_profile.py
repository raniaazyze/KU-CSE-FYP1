"""Create or update a static recognition profile from a reference-experiment export.

Reads the JSON that the reference experiment page exports (five reference captures),
recomputes the mean of the ten joint angles with gesture_utils.average(), and adds a
profile entry to recognition/static_profiles.json in the same format as the existing
ones (angles method, slope 1, threshold 70 by default).

Run from the project root, inside the venv. It PREVIEWS by default; add --apply to write.
    python tools/make_profile.py experiment_F.json
    python tools/make_profile.py experiment_F.json --apply
    python tools/make_profile.py experiment_F.json --lesson-id 23 --apply
"""
import argparse
import json
import shutil
import sys
import math
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import gesture_utils as gu  # noqa: E402

PROFILE_PATH = ROOT / 'recognition' / 'static_profiles.json'
# Fingertip pairs for --tip-contact (MediaPipe tips: thumb 4, index 8, middle 12, ring 16, little 20).
TIP_PAIRS = {'thumb-index': (4, 8), 'thumb-middle': (4, 12), 'thumb-ring': (4, 16), 'thumb-little': (4, 20)}
BACKUP_DIR = ROOT / 'lesson_transfer_backups'


def tip_gap(points, pair):
    """Gap between two fingertips in palm-length units (same measure the app uses)."""
    n = gu.normalize(points)
    return math.sqrt(sum((n[pair[0]][k] - n[pair[1]][k]) ** 2 for k in ('x', 'y', 'z')))


def build_entry(data, path, slope, threshold, hand_override=None, tip_contact=None, tip_margin=0.1):
    refs = data.get('references')
    if not isinstance(refs, list) or len(refs) != 5:
        raise ValueError('Expected exactly 5 reference captures in "references"; found %s.'
                         % (len(refs) if isinstance(refs, list) else 'none'))
    hands = {r.get('hand') for r in refs if r.get('hand')}
    hand = hand_override or (data.get('referenceHand') or (hands.pop() if len(hands) == 1 else None))
    if hand not in ('right', 'left'):
        raise ValueError('Could not tell whether the references are right or left hand.')
    if not hand_override and len({r.get('hand') for r in refs if r.get('hand')} - {hand}):
        raise ValueError('The five references mix right and left hands. Recapture them with one hand.')
    angles = gu.average([r['landmarks'] for r in refs], 'angles')['angles']
    if any(not 0 <= a <= 180 for a in angles) or len(angles) != 10:
        raise ValueError('Computed angles are invalid.')
    stored = (data.get('average') or {}).get('angles')
    if isinstance(stored, list) and len(stored) == 10:
        worst = max(abs(a - b) for a, b in zip(angles, stored))
        if worst > 0.5:
            raise ValueError('Recomputed angles differ from the file\'s own average by %.2f degrees; '
                             'the export may be inconsistent.' % worst)
    sign = (data.get('average') or {}).get('sign_name') or (data.get('original') or {}).get('sign_name')
    if not sign:
        raise ValueError('The export has no sign name.')
    entry = {
        'enabled': True,
        'sign_name': sign,
        'method': 'angles',
        'slope': slope,
        'threshold': threshold,
        'reference': {'angles': angles, 'reference_method': 'mean_joint_angles'},
        'reference_hand': hand,
        'capture_count': 5,
        'source': 'Five reference captures from %s' % path.name,
        'evaluation_scope': '%s-hand %s profile from five captures; not yet validated against '
                            'look-alike wrong poses.' % (hand.capitalize(), sign),
    }
    if tip_contact:
        pair = TIP_PAIRS[tip_contact]
        gaps = [tip_gap(r['landmarks'], pair) for r in refs]
        maximum = max(gaps)
        entry['tip_contact_check'] = {
            'enabled': True,
            'version': 1,
            'name': tip_contact.replace('-', '_') + '_tip_gap',
            'landmarks': list(pair),
            'upper_limit': maximum + tip_margin,
            'reference_maxima': maximum,
            'additive_margin': tip_margin,
            'construction': 'Largest %s tip gap across the five references plus a provisional margin, '
                            'in palm-length units.' % tip_contact,
            'validation_scope': 'Limit built from the five references only; fresh-data evaluation pending.',
        }
    return entry


def db_sign_name(lesson_id):
    """Best effort: the sign name this lesson has in the local database, or None."""
    try:
        import config, pymysql
        conn = pymysql.connect(host=getattr(config, 'MYSQL_HOST', 'localhost'), user=config.MYSQL_USER,
                               password=getattr(config, 'MYSQL_PASSWORD', ''), database=config.MYSQL_DB,
                               charset='utf8mb4')
        try:
            cur = conn.cursor()
            cur.execute('SELECT sign_name FROM LESSONS WHERE lesson_id = %s', (lesson_id,))
            row = cur.fetchone()
            return row[0] if row else ''
        finally:
            conn.close()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='+', type=Path)
    ap.add_argument('--lesson-id', type=int, help='Override the lesson ID stored in the export.')
    ap.add_argument('--hand', choices=('right', 'left'), help='Override the hand recorded in the file, '
                    'for example if the page labelled your right hand as left.')
    ap.add_argument('--tip-contact', choices=sorted(TIP_PAIRS),
                    help='Also require these two fingertips to touch (for example thumb-index for F).')
    ap.add_argument('--tip-margin', type=float, default=0.1,
                    help='Margin added to the largest reference tip gap (palm lengths, default 0.1).')
    ap.add_argument('--slope', type=float, default=1)
    ap.add_argument('--threshold', type=float, default=70)
    ap.add_argument('--overwrite', action='store_true', help='Replace an existing profile for that lesson.')
    ap.add_argument('--no-db-check', action='store_true')
    ap.add_argument('--apply', action='store_true', help='Write changes. Without this, only preview.')
    args = ap.parse_args()
    if len(args.files) > 1 and args.lesson_id is not None:
        sys.exit('--lesson-id can only be used with one file.')

    document = json.loads(PROFILE_PATH.read_text(encoding='utf-8'))
    if document.get('schema_version') != 1 or not isinstance(document.get('lessons'), dict):
        sys.exit('Unexpected recognition/static_profiles.json format; nothing changed.')

    planned, problems = [], []
    for path in args.files:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            lesson_id = args.lesson_id if args.lesson_id is not None else data.get('lesson_id')
            if not isinstance(lesson_id, int):
                raise ValueError('No lesson_id in the file; pass --lesson-id.')
            entry = build_entry(data, path, args.slope, args.threshold, args.hand, args.tip_contact, args.tip_margin)
            if not args.no_db_check:
                local = db_sign_name(lesson_id)
                if local is None:
                    print('  note: could not check the database for lesson %d (continuing).' % lesson_id)
                elif local != entry['sign_name']:
                    raise ValueError('Lesson %d is "%s" in your database but the file is for "%s". '
                                     'Check the lesson ID.' % (lesson_id, local or '(missing)', entry['sign_name']))
            existing = document['lessons'].get(str(lesson_id))
            if existing and not args.overwrite:
                raise ValueError('Lesson %d already has a profile (sign "%s"). Use --overwrite to replace it.'
                                 % (lesson_id, existing.get('sign_name')))
            planned.append((lesson_id, entry, 'UPDATE' if existing else 'ADD'))
        except (ValueError, KeyError, gu.LandmarkError, json.JSONDecodeError, OSError) as exc:
            problems.append('%s: %s' % (path.name, exc))

    for lesson_id, entry, action in planned:
        print('%s lesson %d  sign %s  hand %s  slope %g  threshold %g'
              % (action, lesson_id, entry['sign_name'], entry['reference_hand'], entry['slope'], entry['threshold']))
        print('    angles: ' + ', '.join('%.0f' % a for a in entry['reference']['angles']))
        tc = entry.get('tip_contact_check')
        if tc:
            print('    tip contact %s: reference max gap %.3f + margin %.2f -> upper limit %.3f'
                  % (tc['name'], tc['reference_maxima'], tc['additive_margin'], tc['upper_limit']))
    for p in problems:
        print('PROBLEM ' + p)
    if problems:
        sys.exit('Nothing was written because of the problems above.')
    if not args.apply:
        print('PREVIEW ONLY: nothing changed. Repeat with --apply to write.')
        return
    BACKUP_DIR.mkdir(exist_ok=True)
    backup = BACKUP_DIR / ('static_profiles_%s.json' % time.strftime('%Y%m%d_%H%M%S'))
    shutil.copy2(PROFILE_PATH, backup)
    for lesson_id, entry, _ in planned:
        document['lessons'][str(lesson_id)] = entry
    PROFILE_PATH.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Written. Backup of the old file: %s' % backup.name)


if __name__ == '__main__':
    main()
