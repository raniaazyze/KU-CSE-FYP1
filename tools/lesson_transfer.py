"""Portable static lesson exchange. Run from either project's virtual environment.

No Flask/MediaPipe startup. Uses local config.py and PyMySQL only for database access.
Import previews by default; --apply writes lessons, landmarks, media and profiles.
"""
import argparse
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('sign_name', 'difficulty', 'video_url', 'image_url', 'description', 'hint')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def connect():
    sys.path.insert(0, str(ROOT))
    config = importlib.import_module('config')
    import pymysql
    return pymysql.connect(host=config.MYSQL_HOST, user=config.MYSQL_USER,
                           password=config.MYSQL_PASSWORD, database=config.MYSQL_DB,
                           port=getattr(config, 'MYSQL_PORT', 3306),
                           charset='utf8mb4', autocommit=False)


def profile_path():
    return ROOT / 'recognition' / 'static_profiles.json'


def load_profiles():
    data = read_json(profile_path())
    if data.get('schema_version') != 1 or not isinstance(data.get('lessons'), dict):
        raise ValueError('Unsupported local static_profiles.json format.')
    return data


def unique(rows, description):
    if len(rows) > 1:
        raise ValueError('Ambiguous ' + description + ': duplicate names. Resolve duplicates first.')
    return rows[0] if rows else None


def digest(data):
    return hashlib.sha256(data).hexdigest()


def local_asset(url):
    if not url:
        return None
    parsed = urlsplit(url)
    if parsed.scheme in ('http', 'https') and parsed.netloc:
        return None  # Shared external URLs are kept; no network fetching.
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError('Unsupported demo URL: ' + url)
    relative = parsed.path.lstrip('/')
    if not relative.startswith('static/'):
        raise ValueError('Local demo must be under static/: ' + url)
    path = (ROOT / relative).resolve()
    if not path.is_relative_to((ROOT / 'static').resolve()) or not path.is_file():
        raise ValueError('Missing or unsafe local demo: ' + url)
    return path


def validate_bundle(data):
    if data.get('format') != 'fyp-static-lesson' or data.get('version') != 1:
        raise ValueError('Not a supported static lesson bundle.')
    identity = data.get('identity', {})
    if any(not isinstance(identity.get(k), str) or not identity[k].strip()
           for k in ('language', 'category', 'sign_name')):
        raise ValueError('Language, category and sign name are required.')
    lesson = data.get('lesson', {})
    if set(lesson) != set(FIELDS) or lesson['sign_name'] != identity['sign_name']:
        raise ValueError('Lesson fields or sign name are invalid.')
    for key in ('video_url', 'image_url'):
        if lesson[key] is not None and not isinstance(lesson[key], str):
            raise ValueError('Demo URLs must be strings or null.')
    sys.path.insert(0, str(ROOT))
    from gesture_utils import validate, compare, apply_shape_checks
    landmarks = data.get('gesture', {}).get('landmarks')
    validate(landmarks)
    profile = data.get('recognition_profile', {})
    if (profile.get('sign_name') != identity['sign_name'] or profile.get('method') != 'angles'
            or profile.get('enabled') is not True):
        raise ValueError('An enabled matching angles profile is required. Integrate this sign first.')
    result = compare(landmarks, profile['reference'], 'angles', profile['slope'], profile['threshold'])
    if profile.get('shape_checks', {}).get('enabled'):
        apply_shape_checks(landmarks, result, profile['shape_checks'])
    return data


def export_lessons(connection, ids, language, output):
    profiles = load_profiles()
    output = Path(output)
    documents = []
    cur = connection.cursor()
    try:
        for lesson_id in ids:
            cur.execute('SELECT L.sign_name,L.difficulty,L.video_url,L.image_url,L.description,L.hint,C.name,C.description '
                        'FROM LESSONS L JOIN CATEGORIES C ON C.category_id=L.category_id WHERE L.lesson_id=%s', (lesson_id,))
            row = unique(cur.fetchall(), 'lesson ID')
            if not row:
                raise ValueError('Lesson not found: ' + str(lesson_id))
            cur.execute('SELECT landmark_json FROM GESTURE_DATA WHERE lesson_id=%s', (lesson_id,))
            gesture = unique(cur.fetchall(), 'gesture reference')
            if not gesture:
                raise ValueError('Missing database gesture for lesson ' + str(lesson_id))
            profile = profiles['lessons'].get(str(lesson_id))
            data = {'format': 'fyp-static-lesson', 'version': 1,
                    'identity': {'language': language, 'category': row[6], 'sign_name': row[0]},
                    'category_description': row[7], 'lesson': dict(zip(FIELDS, row[:6])),
                    'gesture': json.loads(gesture[0]), 'recognition_profile': copy.deepcopy(profile), 'assets': []}
            validate_bundle(data)
            assets = []
            for field in ('image_url', 'video_url'):
                source = local_asset(data['lesson'][field])
                if source:
                    content = source.read_bytes()
                    sha = digest(content)
                    name = sha + source.suffix.lower()
                    data['assets'].append({'field': field, 'file': 'media/' + name, 'sha256': sha})
                    assets.append((output / 'media' / name, content))
            key = json.dumps(data['identity'], sort_keys=True, ensure_ascii=False)
            sign = re.sub(r'[^A-Za-z0-9_-]', '_', row[0])[:40] or 'sign'
            name = re.sub(r'[^A-Za-z0-9_-]', '_', language) + '__' + sign + '__' + digest(key.encode())[:8] + '.json'
            documents.append((output / name, data, assets))
        for path, data, assets in documents:
            for asset, content in assets:
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_bytes(content)
            atomic_json(path, data)
            print('EXPORTED', path)
    finally:
        cur.close()


def plan_import(connection, paths, category_name=None):
    plans = []
    seen = set()
    cur = connection.cursor()
    try:
        for path in paths:
            path = Path(path).resolve()
            data = validate_bundle(read_json(path))
            ident = data['identity']
            # This schema has no language column: keep languages in separate categories.
            # Prefixing the language prevents an ASL lesson overwriting a KSL namesake.
            category = category_name or ident['language'] + ' · ' + ident['category']
            key = (category, ident['sign_name'])
            if key in seen:
                raise ValueError('Duplicate target sign in this batch: ' + str(key))
            seen.add(key)
            cur.execute('SELECT category_id FROM CATEGORIES WHERE name=%s', (category,))
            cat = unique(cur.fetchall(), 'category ' + category)
            lesson_id = None
            if cat:
                cur.execute('SELECT lesson_id FROM LESSONS WHERE category_id=%s AND sign_name=%s', (cat[0], ident['sign_name']))
                lesson = unique(cur.fetchall(), 'lesson ' + str(key))
                if lesson:
                    lesson_id = lesson[0]
            media = []
            fields = set()
            for asset in data.get('assets', []):
                field = asset['field']
                if field not in ('image_url', 'video_url') or field in fields:
                    raise ValueError('Invalid or duplicate asset field.')
                fields.add(field)
                source = (path.parent / asset['file']).resolve()
                if not source.is_relative_to(path.parent) or not source.is_file():
                    raise ValueError('Missing or unsafe bundle media file.')
                content = source.read_bytes()
                sha = digest(content)
                if sha != asset['sha256']:
                    raise ValueError('Demo media checksum mismatch.')
                name = sha + source.suffix.lower()
                dest = ROOT / 'static' / 'uploads' / 'shared' / name
                if not dest.resolve().is_relative_to((ROOT / 'static').resolve()):
                    raise ValueError('Unsafe media destination.')
                if dest.exists() and digest(dest.read_bytes()) != sha:
                    raise ValueError('Conflicting shared media file.')
                data['lesson'][field] = '/static/uploads/shared/' + name
                media.append((dest, content))
            for field in ('image_url', 'video_url'):
                if field not in fields:
                    local_asset(data['lesson'][field])  # Existing local path must be available here too.
            plans.append({'data': data, 'category': category, 'category_id': cat[0] if cat else None,
                          'lesson_id': lesson_id, 'media': media})
            print(('UPDATE' if lesson_id is not None else 'ADD'), category, '/', ident['sign_name'],
                  '(local lesson ' + str(lesson_id) + ')' if lesson_id is not None else '')
    finally:
        cur.close()
    return plans


def apply_import(connection, plans):
    profiles = load_profiles()
    original = profile_path().read_bytes()
    backup = ROOT / 'lesson_transfer_backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True)
    (backup / 'static_profiles.json').write_bytes(original)
    snapshots = []
    created_media = []
    profile_written = False
    cur = connection.cursor()
    try:
        for plan in plans:
            data = plan['data']
            cat_id = plan['category_id']
            if cat_id is None:
                cur.execute('SELECT category_id FROM CATEGORIES WHERE name=%s', (plan['category'],))
                found = unique(cur.fetchall(), 'category')
                if found:
                    cat_id = found[0]
                else:
                    cur.execute('INSERT INTO CATEGORIES (name,description) VALUES (%s,%s)',
                                (plan['category'], data.get('category_description')))
                    cat_id = cur.lastrowid
            lesson_id = plan['lesson_id']
            snapshot = {'category': plan['category'], 'lesson_id': lesson_id, 'old_lesson': None, 'old_gestures': []}
            if lesson_id is not None:
                cur.execute('SELECT category_id,sign_name,difficulty,video_url,image_url,description,hint FROM LESSONS WHERE lesson_id=%s', (lesson_id,))
                snapshot['old_lesson'] = cur.fetchone()
                cur.execute('SELECT landmark_json FROM GESTURE_DATA WHERE lesson_id=%s', (lesson_id,))
                snapshot['old_gestures'] = cur.fetchall()
                cur.execute('UPDATE LESSONS SET sign_name=%s,difficulty=%s,video_url=%s,image_url=%s,description=%s,hint=%s WHERE lesson_id=%s',
                            tuple(data['lesson'][k] for k in FIELDS) + (lesson_id,))
            else:
                cur.execute('INSERT INTO LESSONS (category_id,sign_name,difficulty,video_url,image_url,description,hint) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                            (cat_id,) + tuple(data['lesson'][k] for k in FIELDS))
                lesson_id = cur.lastrowid
            snapshots.append(snapshot)
            cur.execute('SELECT landmark_json FROM GESTURE_DATA WHERE lesson_id=%s', (lesson_id,))
            exists = unique(cur.fetchall(), 'gesture')
            payload = json.dumps(data['gesture'], ensure_ascii=False, allow_nan=False)
            if exists:
                cur.execute('UPDATE GESTURE_DATA SET landmark_json=%s WHERE lesson_id=%s', (payload, lesson_id))
            else:
                cur.execute('INSERT INTO GESTURE_DATA (lesson_id,landmark_json) VALUES (%s,%s)', (lesson_id, payload))
            profiles['lessons'][str(lesson_id)] = data['recognition_profile']
            for dest, content in plan['media']:
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(content)
                    created_media.append(dest)
            print('MAPPED', data['identity']['sign_name'], '-> local lesson', lesson_id)
        atomic_json(backup / 'previous_lessons.json', snapshots)
        # Flask must be stopped: MySQL and a JSON file cannot share one transaction.
        atomic_json(profile_path(), profiles)
        profile_written = True
        connection.commit()
    except Exception:
        connection.rollback()
        if profile_written:
            profile_path().write_bytes(original)
        for dest in created_media:
            dest.unlink(missing_ok=True)
        raise
    finally:
        cur.close()
    print('IMPORTED. Local backups:', backup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    exp = commands.add_parser('export')
    exp.add_argument('--lesson-ids', type=int, nargs='+', required=True)
    exp.add_argument('--language', required=True, help='For example ASL; this describes the actual signs.')
    exp.add_argument('--output', type=Path, default=ROOT / 'shared_lessons')
    imp = commands.add_parser('import')
    imp.add_argument('--files', type=Path, nargs='+', required=True)
    imp.add_argument('--category-name', help='Explicit local category to use; only combine signs of the SAME language.')
    imp.add_argument('--apply', action='store_true', help='Write changes. Without this, only preview.')
    args = parser.parse_args()
    connection = connect()
    try:
        if args.command == 'export':
            export_lessons(connection, args.lesson_ids, args.language, args.output)
        else:
            plans = plan_import(connection, args.files, args.category_name)
            if args.apply:
                apply_import(connection, plans)
            else:
                print('PREVIEW ONLY: nothing changed. Repeat with --apply to import.')
    finally:
        connection.rollback()  # End any read-only transaction; committed writes remain committed.
        connection.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Lesson transfer failed:', str(error), file=sys.stderr)
        sys.exit(1)
