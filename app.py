from flask import Flask, request, jsonify, send_file
from flask_mysqldb import MySQL
from flask_cors import CORS
import bcrypt
import config
import json

app = Flask(__name__)
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
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM USERS WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close()
    if not user:
        return jsonify({'error': '이메일을 찾을 수 없습니다 / Email not found'}), 401
    try:
        password_match = bcrypt.checkpw(
            password.encode('utf-8'),
            user[3].encode('utf-8')
        )
    except Exception:
        password_match = False
    if password_match:
        return jsonify({
            'message': '로그인 성공 / Login successful',
            'user_id': user[0],
            'username': user[1],
            'role': user[4]
        }), 200
    return jsonify({'error': '비밀번호가 틀렸습니다 / Wrong password'}), 401

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data['username']
    email = data['email']
    password = data['password']
    role = data.get('role', 'user')

    # Check duplicate email
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM USERS WHERE email = %s", (email,))
    existing = cur.fetchone()
    if existing:
        cur.close()
        return jsonify({'error': '이미 등록된 이메일입니다 / Email already registered'}), 400

    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    hashed_str = hashed.decode('utf-8')
    try:
        cur.execute("INSERT INTO USERS (username, email, password, role) VALUES (%s, %s, %s, %s)",
                    (username, email, hashed_str, role))
        mysql.connection.commit()
        cur.close()
        return jsonify({'message': '가입 완료 / Registered'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

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
    return jsonify([{'lesson_id': r[0], 'sign_name': r[2], 'difficulty': r[3], 'description': r[6], 'hint': r[7]} for r in rows])

@app.route('/api/lessons', methods=['POST'])
def add_lesson():
    data = request.get_json()
    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO LESSONS (category_id, sign_name, difficulty, description, hint) VALUES (%s,%s,%s,%s,%s)",
                (data['category_id'], data['sign_name'], data['difficulty'], data['description'], data['hint']))
    mysql.connection.commit()
    cur.close()
    return jsonify({'message': '레슨 추가 완료 / Lesson added'}), 201

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
    cur.execute("""SELECT UP.progress_id, L.sign_name, UP.score, UP.status, UP.attempted_at
                   FROM USER_PROGRESS UP
                   JOIN LESSONS L ON UP.lesson_id = L.lesson_id
                   WHERE UP.user_id = %s""", (user_id,))
    rows = cur.fetchall()
    cur.close()
    return jsonify([{'progress_id': r[0], 'sign_name': r[1], 'score': r[2], 'status': r[3], 'attempted_at': str(r[4])} for r in rows])

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
    # Total completed lessons
    cur.execute("""SELECT COUNT(*) FROM USER_PROGRESS 
                   WHERE user_id = %s AND status = 'completed'""", (user_id,))
    completed = cur.fetchone()[0]
    # Average score
    cur.execute("""SELECT AVG(score) FROM USER_PROGRESS 
                   WHERE user_id = %s AND status = 'completed'""", (user_id,))
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
            'total_users': total_users,
            'total_lessons': total_lessons,
            'completion_rate': completion_rate
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
            'completed': r[2],
            'avg_score': r[3] or 0,
            'total_attempts': r[4]
        } for r in rows], ensure_ascii=False),
        status=200,
        mimetype='application/json'
    )
    
if __name__ == '__main__':
    app.run(debug=True)