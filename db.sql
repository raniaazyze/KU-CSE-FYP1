CREATE DATABASE sueo_platform;
USE sueo_platform;

CREATE TABLE USERS (
  user_id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(100) NOT NULL,
  email VARCHAR(150) NOT NULL UNIQUE,
  password VARCHAR(255) NOT NULL,
  role ENUM('user', 'admin') DEFAULT 'user',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE CATEGORIES (
  category_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  description VARCHAR(255)
);

CREATE TABLE LESSONS (
  lesson_id INT AUTO_INCREMENT PRIMARY KEY,
  category_id INT,
  sign_name VARCHAR(100) NOT NULL,
  difficulty ENUM('쉬움', '보통', '어려움') DEFAULT '쉬움',
  video_url VARCHAR(255),
  image_url VARCHAR(255),
  description TEXT,
  hint TEXT,
  FOREIGN KEY (category_id) REFERENCES CATEGORIES(category_id)
);

CREATE TABLE GESTURE_DATA (
  gesture_id INT AUTO_INCREMENT PRIMARY KEY,
  lesson_id INT UNIQUE,
  landmark_json TEXT,
  FOREIGN KEY (lesson_id) REFERENCES LESSONS(lesson_id)
);

CREATE TABLE USER_PROGRESS (
  progress_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT,
  lesson_id INT,
  score INT,
  status ENUM('not_started', 'in_progress', 'completed') DEFAULT 'not_started',
  attempted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES USERS(user_id),
  FOREIGN KEY (lesson_id) REFERENCES LESSONS(lesson_id)
);

INSERT INTO CATEGORIES (name, description) VALUES
('지문자', 'Basic Fingerspelling'),
('숫자', 'Numbers'),
('인사', 'Greetings'),
('일상', 'Daily Expressions');

INSERT INTO USERS (username, email, password, role) VALUES
('admin', 'admin@sueo.com', 'admin1234', 'admin'),
('ruzhan', 'ruzhan@email.com', 'pass1234', 'user'),
('rania', 'rania@email.com', 'pass1234', 'user');

INSERT INTO LESSONS (category_id, sign_name, difficulty, description, hint) VALUES
(1, 'A', '쉬움', '손을 주먹 쥐고 엄지를 옆으로 세웁니다.', '엄지가 옆을 향해야 해요'),
(1, 'B', '쉬움', '손가락 네 개를 붙여 위로 펴고 엄지는 접습니다.', '손가락을 붙여주세요'),
(2, '1', '쉬움', '검지 손가락만 펴서 위를 가리킵니다.', '검지만 펴세요'),
(3, '안녕하세요', '쉬움', '손을 위로 들어 좌우로 흔드세요.', '손을 더 크게 흔들어보세요'),
(4, '밥', '보통', '손을 입 방향으로 가져갑니다.', '손을 입쪽으로');

SELECT * FROM USERS;
SELECT * FROM CATEGORIES;
SELECT * FROM LESSONS;

USE sueo_platform;
UPDATE USERS SET password = '$2b$12$G0uSPq2rec.f6.w6cs6pcOm.qdsg530V.TmnXRCF8otTjQkfpFSBO' WHERE email = 'admin@sueo.com';
UPDATE USERS SET password = '$2b$12$G0uSPq2rec.f6.w6cs6pcOm.qdsg530V.TmnXRCF8otTjQkfpFSBO' WHERE email = 'ruzhan@email.com';
UPDATE USERS SET password = '$2b$12$G0uSPq2rec.f6.w6cs6pcOm.qdsg530V.TmnXRCF8otTjQkfpFSBO' WHERE email = 'rania@email.com';

SELECT email, password FROM USERS;