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
    password = data['password'].encode('utf-8')
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM USERS WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close()
    if user and bcrypt.checkpw(password, user[3].encode('utf-8')):
        return jsonify({
            'message': '로그인 성공 / Login successful',
            'user_id': user[0],
            'username': user[1],
            'role': user[4]
        }), 200
    return jsonify({'error': '잘못된 자격증명 / Invalid credentials'}), 401

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data['username']
    email = data['email']
    password = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt())
    role = data.get('role', 'user')
    try:
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO USERS (username, email, password, role) VALUES (%s, %s, %s, %s)",
                    (username, email, password, role))
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

if __name__ == '__main__':
    app.run(debug=True)