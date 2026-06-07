-- ============================================================
--  수어 학습 플랫폼 / Sign Language Learning Platform
--  Database Setup Script
--  Last Updated: 2026-06-03
-- ============================================================

-- ── STEP 1: CREATE & SELECT DATABASE ──────────────────────
CREATE DATABASE IF NOT EXISTS sueo_platform;
USE sueo_platform;


-- ── STEP 2: CREATE TABLES ─────────────────────────────────

-- Users table (학습자 & 관리자)
CREATE TABLE USERS (
  user_id    INT          AUTO_INCREMENT PRIMARY KEY,
  username   VARCHAR(100) NOT NULL,
  email      VARCHAR(150) NOT NULL UNIQUE,
  password   VARCHAR(255) NOT NULL,                          -- bcrypt hashed
  role       ENUM('user', 'admin') DEFAULT 'user',
  created_at DATETIME     DEFAULT CURRENT_TIMESTAMP
);

-- Categories table (카테고리)
CREATE TABLE CATEGORIES (
  category_id INT          AUTO_INCREMENT PRIMARY KEY,
  name        VARCHAR(100) NOT NULL,
  description VARCHAR(255)
);

-- Lessons table (레슨)
CREATE TABLE LESSONS (
  lesson_id   INT          AUTO_INCREMENT PRIMARY KEY,
  category_id INT,
  sign_name   VARCHAR(100) NOT NULL,
  difficulty  ENUM('쉬움', '보통', '어려움') DEFAULT '쉬움',
  video_url   VARCHAR(255),                                  -- demo video path
  image_url   VARCHAR(255),                                  -- demo image path
  description TEXT,
  hint        TEXT,
  FOREIGN KEY (category_id) REFERENCES CATEGORIES(category_id)
);

-- Gesture Data table (랜드마크 JSON)
CREATE TABLE GESTURE_DATA (
  gesture_id    INT  AUTO_INCREMENT PRIMARY KEY,
  lesson_id     INT  UNIQUE,
  landmark_json TEXT,                                        -- 21-point MediaPipe JSON
  FOREIGN KEY (lesson_id) REFERENCES LESSONS(lesson_id)
);

-- User Progress table (학습 진행도)
CREATE TABLE USER_PROGRESS (
  progress_id  INT      AUTO_INCREMENT PRIMARY KEY,
  user_id      INT,
  lesson_id    INT,
  score        INT,
  status       ENUM('not_started', 'in_progress', 'completed') DEFAULT 'not_started',
  attempted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id)   REFERENCES USERS(user_id),
  FOREIGN KEY (lesson_id) REFERENCES LESSONS(lesson_id)
);


-- ── STEP 3: INSERT SAMPLE DATA ────────────────────────────

-- Categories
INSERT INTO CATEGORIES (name, description) VALUES
  ('지문자', 'Basic Fingerspelling'),
  ('숫자',   'Numbers'),
  ('인사',   'Greetings'),
  ('일상',   'Daily Expressions');

-- Users (passwords will be updated with bcrypt hash in Step 4)
INSERT INTO USERS (username, email, password, role) VALUES
  ('admin',  'admin@sueo.com',      'TEMP_REPLACE', 'admin'),
  ('ruzhan', 'ruzhan@email.com',    'TEMP_REPLACE', 'user'),
  ('rania',  'rania@email.com',     'TEMP_REPLACE', 'user');

-- Lessons
INSERT INTO LESSONS (category_id, sign_name, difficulty, description, hint) VALUES
  (1, 'A',      '쉬움', '손을 주먹 쥐고 엄지를 옆으로 세웁니다.',         '엄지가 옆을 향해야 해요'),
  (1, 'B',      '쉬움', '손가락 네 개를 붙여 위로 펴고 엄지는 접습니다.', '손가락을 붙여주세요'),
  (2, '1',      '쉬움', '검지 손가락만 펴서 위를 가리킵니다.',             '검지만 펴세요'),
  (3, '안녕하세요', '쉬움', '손을 위로 들어 좌우로 흔드세요.',             '손을 더 크게 흔들어보세요'),
  (4, '밥',     '보통', '손을 입 방향으로 가져갑니다.',                    '손을 입쪽으로');


-- ── STEP 4: UPDATE PASSWORDS WITH BCRYPT HASH ────────────
--  Run this Python snippet first to generate your hash:
--
--    import bcrypt
--    password = 'test1234'
--    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
--    print(hashed.decode('utf-8'))
--
--  Then replace YOUR_BCRYPT_HASH_HERE below with the output:

UPDATE USERS SET password = '$2b$12$G0uSPq2rec.f6.w6cs6pcOm.qdsg530V.TmnXRCF8otTjQkfpFSBO' WHERE email = 'admin@sueo.com';
UPDATE USERS SET password = '$2b$12$G0uSPq2rec.f6.w6cs6pcOm.qdsg530V.TmnXRCF8otTjQkfpFSBO' WHERE email = 'ruzhan@email.com';
UPDATE USERS SET password = '$2b$12$G0uSPq2rec.f6.w6cs6pcOm.qdsg530V.TmnXRCF8otTjQkfpFSBO' WHERE email = 'rania@email.com';
-- NOTE: Above hash = 'test1234' — change before production!


-- ── STEP 5: VERIFY DATA ───────────────────────────────────

-- Check all tables
SELECT user_id, username, email, role, created_at FROM USERS;
SELECT * FROM CATEGORIES;
SELECT lesson_id, category_id, sign_name, difficulty FROM LESSONS;
SELECT gesture_id, lesson_id FROM GESTURE_DATA;
SELECT progress_id, user_id, lesson_id, score, status FROM USER_PROGRESS;

-- Check passwords are hashed (should start with $2b$)
SELECT email, LEFT(password, 10) AS password_preview FROM USERS;

-- Check lesson counts per category
SELECT c.name, COUNT(l.lesson_id) AS lesson_count
FROM CATEGORIES c
LEFT JOIN LESSONS l ON c.category_id = l.category_id
GROUP BY c.category_id, c.name;

-- Check gesture data coverage
SELECT l.sign_name, 
       CASE WHEN g.gesture_id IS NOT NULL THEN '✅ Has Data' ELSE '❌ Missing' END AS gesture_status
FROM LESSONS l
LEFT JOIN GESTURE_DATA g ON l.lesson_id = g.lesson_id;

ALTER TABLE USERS ADD COLUMN streak INT DEFAULT 0;
ALTER TABLE USERS ADD COLUMN last_active DATE DEFAULT NULL;


-- ── QUICK REFERENCE ───────────────────────────────────────
--
--  Table Overview:
--  ┌─────────────────┬──────────────────────────────────────┐
--  │ Table           │ Purpose                              │
--  ├─────────────────┼──────────────────────────────────────┤
--  │ USERS           │ Learners & admins (bcrypt passwords) │
--  │ CATEGORIES      │ Sign categories (지문자, 숫자, etc.) │
--  │ LESSONS         │ Individual signs with description    │
--  │ GESTURE_DATA    │ MediaPipe 21-point landmark JSON     │
--  │ USER_PROGRESS   │ Scores & completion per user/lesson  │
--  └─────────────────┴──────────────────────────────────────┘
--
--  Default Login:
--  Admin  → admin@sueo.com    / test1234
--  User   → ruzhan@email.com  / test1234
--
--  Role Values:   'user' | 'admin'
--  Status Values: 'not_started' | 'in_progress' | 'completed'
--  Difficulty:    '쉬움' | '보통' | '어려움'
-- ============================================================