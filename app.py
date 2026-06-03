from flask import Flask, request, jsonify, send_file
from flask_mysqldb import MySQL
from flask_cors import CORS
from werkzeug.utils import secure_filename
import bcrypt
import config
import json
import os
import cv2
import mediapipe as mp
import numpy as np
import base64
import json

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 30 * 1024 * 1024  # 30MB max
ALLOWED_VIDEO = {'mp4', 'mov', 'avi', 'webm'}
ALLOWED_IMAGE = {'jpg', 'jpeg', 'png', 'gif'}

def allowed_file(filename, allowed):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed
app.config['JSON_AS_ASCII'] = False
app.json.ensure_ascii = False
CORS(app)

app.config['MYSQL_HOST'] = config.MYSQL_HOST
app.config['MYSQL_USER'] = config.MYSQL_USER
app.config['MYSQL_PASSWORD'] = config.MYSQL_PASSWORD
app.config['MYSQL_DB'] = config.MYSQL_DB
app.secret_key = config.SECRET_KEY

mysql = MySQL(app)

@app.route('/')
def index():
    return send_file('sign_language_platform_v2.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data['email']
    password = data['password']
    requested_role = data.get('role', 'user')

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM USERS WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close()

    if not user:
        return app.response_class(
            response=json.dumps({'error': '이메일을 찾을 수 없습니다 / Email not found'}, ensure_ascii=False),
            status=401,
            mimetype='application/json'
        )

    # Check role mismatch BEFORE password
    if user[4] != requested_role:
        if requested_role == 'admin':
            return app.response_class(
                response=json.dumps({'error': '관리자 계정이 아닙니다 / This is not an admin account'}, ensure_ascii=False),
                status=403,
                mimetype='application/json'
            )
        else:
            return app.response_class(
                response=json.dumps({'error': '학습자 계정이 아닙니다 / This is not a learner account'}, ensure_ascii=False),
                status=403,
                mimetype='application/json'
            )

    # Check password
    try:
        password_match = bcrypt.checkpw(
            password.encode('utf-8'),
            user[3].encode('utf-8')
        )
    except Exception:
        password_match = False

    if password_match:
        return app.response_class(
            response=json.dumps({
                'message': '로그인 성공 / Login successful',
                'user_id': user[0],
                'username': user[1],
                'role': user[4]
            }, ensure_ascii=False),
            status=200,
            mimetype='application/json'
        )
    return app.response_class(
        response=json.dumps({'error': '비밀번호가 틀렸습니다 / Wrong password'}, ensure_ascii=False),
        status=401,
        mimetype='application/json'
    )

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data['username']
    email = data['email']
    password = data['password']
    role = 'user'  # ← Always force role to 'user' on public registration

    # Check duplicate email
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM USERS WHERE email = %s", (email,))
    existing = cur.fetchone()
    if existing:
        cur.close()
        return app.response_class(
            response=json.dumps({'error': '이미 등록된 이메일입니다 / Email already registered'}, ensure_ascii=False),
            status=400,
            mimetype='application/json'
        )

    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    hashed_str = hashed.decode('utf-8')
    try:
        cur.execute("INSERT INTO USERS (username, email, password, role) VALUES (%s, %s, %s, %s)",
                    (username, email, hashed_str, role))
        mysql.connection.commit()
        cur.close()
        return app.response_class(
            response=json.dumps({'message': '가입 완료 / Registered'}, ensure_ascii=False),
            status=201,
            mimetype='application/json'
        )
    except Exception as e:
        return app.response_class(
            response=json.dumps({'error': str(e)}, ensure_ascii=False),
            status=400,
            mimetype='application/json'
        )

@app.route('/api/categories', methods=['GET'])
def get_categories():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM CATEGORIES")
    rows = cur.fetchall()
    cur.close()
    return jsonify([{'category_id': r[0], 'name': r[1], 'description': r[2]} for r in rows])

@app.route('/api/lessons/<int:category_id>', methods=['GET'])
def get_lessons(category_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM LESSONS WHERE category_id = %s", (category_id,))
    rows = cur.fetchall()
    cur.close()
    return app.response_class(
        response=json.dumps([{
            'lesson_id': r[0],
            'sign_name': r[2],
            'difficulty': r[3],
            'video_url': r[4] or '',
            'image_url': r[5] or '',
            'description': r[6],
            'hint': r[7]
        } for r in rows], ensure_ascii=False),
        status=200,
        mimetype='application/json'
    )

@app.route('/api/lessons', methods=['POST'])
def add_lesson():
    data = request.get_json()
    cur = mysql.connection.cursor()
    cur.execute("""INSERT INTO LESSONS (category_id, sign_name, difficulty, description, hint)
                   VALUES (%s, %s, %s, %s, %s)""",
                (data['category_id'], data['sign_name'], data['difficulty'],
                 data['description'], data['hint']))
    mysql.connection.commit()
    lesson_id = cur.lastrowid
    cur.close()
    return app.response_class(
        response=json.dumps({
            'message': '레슨 추가 완료 / Lesson added',
            'lesson_id': lesson_id
        }, ensure_ascii=False),
        status=201,
        mimetype='application/json'
    )

@app.route('/api/lessons/<int:lesson_id>', methods=['PUT'])
def edit_lesson(lesson_id):
    data = request.get_json()
    cur = mysql.connection.cursor()
    cur.execute("UPDATE LESSONS SET sign_name=%s, difficulty=%s, description=%s, hint=%s WHERE lesson_id=%s",
                (data['sign_name'], data['difficulty'], data['description'], data['hint'], lesson_id))
    mysql.connection.commit()
    cur.close()
    return jsonify({'message': '수정 완료 / Updated'})

@app.route('/api/lessons/<int:lesson_id>', methods=['DELETE'])
def delete_lesson(lesson_id):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM USER_PROGRESS WHERE lesson_id = %s", (lesson_id,))
    cur.execute("DELETE FROM GESTURE_DATA WHERE lesson_id = %s", (lesson_id,))
    cur.execute("DELETE FROM LESSONS WHERE lesson_id = %s", (lesson_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({'message': '삭제 완료 / Deleted'})

@app.route('/api/progress', methods=['POST'])
def save_progress():
    data = request.get_json()
    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO USER_PROGRESS (user_id, lesson_id, score, status) VALUES (%s,%s,%s,%s)",
                (data['user_id'], data['lesson_id'], data['score'], data['status']))
    mysql.connection.commit()
    cur.close()
    return jsonify({'message': '진행도 저장 / Progress saved'}), 201

@app.route('/api/progress/<int:user_id>', methods=['GET'])
def get_progress(user_id):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT UP.lesson_id, L.sign_name,
               MAX(UP.score) as best_score,
               UP.status,
               MAX(UP.attempted_at) as last_attempt,
               L.category_id
        FROM USER_PROGRESS UP
        JOIN LESSONS L ON UP.lesson_id = L.lesson_id
        WHERE UP.user_id = %s AND UP.status = 'completed'
        GROUP BY UP.lesson_id, L.sign_name, UP.status, L.category_id
        ORDER BY last_attempt DESC
    """, (user_id,))
    rows = cur.fetchall()
    cur.close()
    return app.response_class(
        response=json.dumps([{
            'lesson_id': r[0],
            'sign_name': r[1],
            'score': int(r[2]) if r[2] else 0,
            'status': r[3],
            'attempted_at': str(r[4]),
            'category_id': r[5]
        } for r in rows], ensure_ascii=False),
        status=200,
        mimetype='application/json'
    )

@app.route('/api/users', methods=['GET'])
def get_users():
    cur = mysql.connection.cursor()
    cur.execute("SELECT user_id, username, email, role, created_at FROM USERS")
    rows = cur.fetchall()
    cur.close()
    return jsonify([{'user_id': r[0], 'username': r[1], 'email': r[2], 'role': r[3], 'created_at': str(r[4])} for r in rows])

# ── GET USER DASHBOARD STATS ──
@app.route('/api/stats/<int:user_id>', methods=['GET'])
def get_user_stats(user_id):
    cur = mysql.connection.cursor()

    # Count UNIQUE completed lessons only
    cur.execute("""
        SELECT COUNT(DISTINCT lesson_id) 
        FROM USER_PROGRESS 
        WHERE user_id = %s AND status = 'completed'
    """, (user_id,))
    completed = cur.fetchone()[0]

    # Average of best scores per lesson
    cur.execute("""
        SELECT AVG(best_score) FROM (
            SELECT MAX(score) as best_score
            FROM USER_PROGRESS
            WHERE user_id = %s AND status = 'completed'
            GROUP BY lesson_id
        ) as scores
    """, (user_id,))
    avg = cur.fetchone()[0]
    avg_score = round(avg) if avg else 0

    # Total lessons available
    cur.execute("SELECT COUNT(*) FROM LESSONS")
    total = cur.fetchone()[0]
    cur.close()

    return app.response_class(
        response=json.dumps({
            'completed': completed,
            'avg_score': avg_score,
            'total_lessons': total,
            'remaining': total - completed
        }, ensure_ascii=False),
        status=200,
        mimetype='application/json'
    )

# ── GET ADMIN DASHBOARD STATS ──
@app.route('/api/admin/stats', methods=['GET'])
def get_admin_stats():
    cur = mysql.connection.cursor()
    # Total users (excluding admin)
    cur.execute("SELECT COUNT(*) FROM USERS WHERE role = 'user'")
    total_users = cur.fetchone()[0]
    # Total lessons
    cur.execute("SELECT COUNT(*) FROM LESSONS")
    total_lessons = cur.fetchone()[0]
    # Overall completion rate
    cur.execute("SELECT COUNT(*) FROM USER_PROGRESS WHERE status = 'completed'")
    completed = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM USER_PROGRESS")
    total_attempts = cur.fetchone()[0]
    completion_rate = round((completed / total_attempts * 100)) if total_attempts > 0 else 0
    cur.close()
    return app.response_class(
        response=json.dumps({
            'total_users': int(total_users),
            'total_lessons': int(total_lessons),
            'completion_rate': int(completion_rate) if completion_rate else 0
        }, ensure_ascii=False),
        status=200,
        mimetype='application/json'
    )

# ── GET ALL USERS PROGRESS (admin) ──
@app.route('/api/admin/progress', methods=['GET'])
def get_all_progress():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT U.user_id, U.username,
               COUNT(CASE WHEN UP.status = 'completed' THEN 1 END) as completed,
               ROUND(AVG(CASE WHEN UP.status = 'completed' THEN UP.score END)) as avg_score,
               COUNT(UP.progress_id) as total_attempts
        FROM USERS U
        LEFT JOIN USER_PROGRESS UP ON U.user_id = UP.user_id
        WHERE U.role = 'user'
        GROUP BY U.user_id, U.username
        ORDER BY completed DESC
    """)
    rows = cur.fetchall()
    cur.close()
    return app.response_class(
    response=json.dumps([{
        'user_id': r[0],
        'username': r[1],
        'completed': int(r[2]) if r[2] else 0,
        'avg_score': int(r[3]) if r[3] else 0,
        'total_attempts': int(r[4]) if r[4] else 0
    } for r in rows], ensure_ascii=False),
    status=200,
    mimetype='application/json'
)
    
# ── UPLOAD GESTURE DATA ──
@app.route('/api/gesture', methods=['POST'])
def upload_gesture():
    data = request.get_json()
    lesson_id = data['lesson_id']
    landmark_json = data['landmark_json']
    try:
        cur = mysql.connection.cursor()
        # Check if gesture data already exists for this lesson
        cur.execute("SELECT * FROM GESTURE_DATA WHERE lesson_id = %s", (lesson_id,))
        existing = cur.fetchone()
        if existing:
            # Update existing
            cur.execute("UPDATE GESTURE_DATA SET landmark_json = %s WHERE lesson_id = %s",
                       (landmark_json, lesson_id))
        else:
            # Insert new
            cur.execute("INSERT INTO GESTURE_DATA (lesson_id, landmark_json) VALUES (%s, %s)",
                       (lesson_id, landmark_json))
        mysql.connection.commit()
        cur.close()
        return app.response_class(
            response=json.dumps({'message': '제스처 데이터 저장 완료 / Gesture data saved'}, ensure_ascii=False),
            status=201,
            mimetype='application/json'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ── GET GESTURE DATA BY LESSON ──
@app.route('/api/gesture/<int:lesson_id>', methods=['GET'])
def get_gesture(lesson_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM GESTURE_DATA WHERE lesson_id = %s", (lesson_id,))
    row = cur.fetchone()
    cur.close()
    if row:
        return app.response_class(
            response=json.dumps({
                'gesture_id': row[0],
                'lesson_id': row[1],
                'landmark_json': row[2]
            }, ensure_ascii=False),
            status=200,
            mimetype='application/json'
        )
    return jsonify({'error': '제스처 데이터 없음 / No gesture data found'}), 404

# ── MEDIAPIPE SETUP ──
mp_hands = mp.solutions.hands
hands_detector = mp_hands.Hands(
    static_image_mode=True,
    max_num_hands=1,
    min_detection_confidence=0.5
)

def calculate_similarity(user_landmarks, ref_landmarks):
    """Calculate similarity between two sets of landmarks"""
    if not user_landmarks or not ref_landmarks:
        return 0
    
    try:
        # Normalize landmarks relative to wrist (point 0)
        def normalize(landmarks):
            wrist = landmarks[0]
            normalized = []
            for lm in landmarks:
                normalized.append({
                    'x': lm['x'] - wrist['x'],
                    'y': lm['y'] - wrist['y'],
                    'z': lm['z'] - wrist['z']
                })
            return normalized

        user_norm = normalize(user_landmarks)
        ref_norm = normalize(ref_landmarks)

        # Calculate distance between each landmark
        total_distance = 0
        for u, r in zip(user_norm, ref_norm):
            dist = (
                (u['x'] - r['x']) ** 2 +
                (u['y'] - r['y']) ** 2 +
                (u['z'] - r['z']) ** 2
            ) ** 0.5
            total_distance += dist

        # Average distance across all 21 points
        avg_distance = total_distance / len(user_norm)

        # Convert to similarity score (0-100)
        # Lower distance = higher similarity
        similarity = max(0, 100 - (avg_distance * 300))
        return round(similarity)

    except Exception as e:
        print(f"Similarity error: {e}")
        return 0

# ── ANALYZE GESTURE FROM WEBCAM FRAME ──
@app.route('/api/analyze', methods=['POST'])
def analyze_gesture():
    try:
        data = request.get_json()
        lesson_id = data['lesson_id']
        image_data = data['image']  # base64 image from browser

        # Decode base64 image
        image_data = image_data.split(',')[1]
        image_bytes = base64.b64decode(image_data)
        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({'error': 'Invalid image'}), 400

        # Run MediaPipe on the frame
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands_detector.process(rgb)

        if not result.multi_hand_landmarks:
            return app.response_class(
                response=json.dumps({
                    'detected': False,
                    'message': '손이 감지되지 않았습니다 / No hand detected',
                    'score': 0
                }, ensure_ascii=False),
                status=200,
                mimetype='application/json'
            )

        # Extract user landmarks
        user_landmarks = []
        for lm in result.multi_hand_landmarks[0].landmark:
            user_landmarks.append({
                'x': round(lm.x, 4),
                'y': round(lm.y, 4),
                'z': round(lm.z, 4)
            })

        # Get reference landmarks from DB
        cur = mysql.connection.cursor()
        cur.execute("SELECT landmark_json FROM GESTURE_DATA WHERE lesson_id = %s", (lesson_id,))
        row = cur.fetchone()
        cur.close()

        if not row:
            return app.response_class(
                response=json.dumps({
                    'detected': True,
                    'message': '기준 데이터 없음 / No reference data',
                    'score': 0
                }, ensure_ascii=False),
                status=200,
                mimetype='application/json'
            )

        # Parse reference landmarks
        ref_data = json.loads(row[0])
        ref_landmarks = ref_data['landmarks']

        # Calculate similarity
        score = calculate_similarity(user_landmarks, ref_landmarks)

        return app.response_class(
            response=json.dumps({
                'detected': True,
                'score': score,
                'message': '정답! / Correct!' if score >= 70 else '다시 시도 / Try Again'
            }, ensure_ascii=False),
            status=200,
            mimetype='application/json'
        )

    except Exception as e:
        print(f"Analysis error: {e}")
        return jsonify({'error': str(e)}), 500
    
# ── UPLOAD DEMO MEDIA ──
@app.route('/api/upload/media', methods=['POST'])
def upload_media():
    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다 / No file'}), 400
    
    file = request.files['file']
    lesson_id = request.form.get('lesson_id')
    
    if file.filename == '':
        return jsonify({'error': '파일을 선택해주세요 / No file selected'}), 400
    
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    
    if ext in ALLOWED_VIDEO:
        folder = 'static/uploads/videos'
        media_type = 'video'
    elif ext in ALLOWED_IMAGE:
        folder = 'static/uploads/images'
        media_type = 'image'
    else:
        return jsonify({'error': '지원하지 않는 파일 형식 / Unsupported file type'}), 400
    
    os.makedirs(folder, exist_ok=True)
    filename = secure_filename(f"lesson_{lesson_id}_{file.filename}")
    filepath = os.path.join(folder, filename)
    file.save(filepath)
    
    # Update lesson in DB with media path
    url = f"/{folder}/{filename}"
    cur = mysql.connection.cursor()
    if media_type == 'video':
        cur.execute("UPDATE LESSONS SET video_url = %s WHERE lesson_id = %s", (url, lesson_id))
    else:
        cur.execute("UPDATE LESSONS SET image_url = %s WHERE lesson_id = %s", (url, lesson_id))
    mysql.connection.commit()
    cur.close()
    
    return app.response_class(
        response=json.dumps({
            'message': '업로드 완료 / Upload successful',
            'url': url,
            'type': media_type
        }, ensure_ascii=False),
        status=200,
        mimetype='application/json'
    )

# ── SERVE STATIC FILES ──
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_file(f'static/{filename}')

# ── EXTRACT LANDMARKS FROM IMAGE ──
@app.route('/api/extract-landmarks', methods=['POST'])
def extract_landmarks():
    try:
        data = request.get_json()
        image_data = data['image'].split(',')[1]
        image_bytes = base64.b64decode(image_data)
        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({'detected': False, 'error': 'Invalid image'}), 400

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands_detector.process(rgb)

        if not result.multi_hand_landmarks:
            return app.response_class(
                response=json.dumps({
                    'detected': False,
                    'message': '손이 감지되지 않았습니다 / No hand detected'
                }, ensure_ascii=False),
                status=200,
                mimetype='application/json'
            )

        landmarks = []
        for idx, lm in enumerate(result.multi_hand_landmarks[0].landmark):
            landmarks.append({
                'id': idx,
                'x': round(lm.x, 4),
                'y': round(lm.y, 4),
                'z': round(lm.z, 4)
            })

        return app.response_class(
            response=json.dumps({
                'detected': True,
                'landmarks': landmarks
            }, ensure_ascii=False),
            status=200,
            mimetype='application/json'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
if __name__ == '__main__':
    app.run(debug=True)