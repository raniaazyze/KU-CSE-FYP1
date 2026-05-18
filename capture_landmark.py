import cv2
import mediapipe as mp
import json
import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.5
)

os.makedirs('gesture_data', exist_ok=True)

def put_korean_text(frame, text, position, font_size=24, color=(0, 255, 255)):
    img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", font_size)
    except:
        font = ImageFont.load_default()
    draw.text(position, text, font=font, fill=color)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

def capture_landmark(sign_name, category):
    cap = cv2.VideoCapture(0)
    landmark_data = None

    print(f"\n📸 Capturing: {sign_name}")
    print("✋ Show your hand and press SPACE to capture")
    print("Press Q to cancel\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb)

        # Korean text for sign name
        frame = put_korean_text(frame, f'수어: {sign_name}', (10, 10), font_size=28, color=(0, 255, 255))
        frame = put_korean_text(frame, 'SPACE = 캡처  |  Q = 취소', (10, 50), font_size=20, color=(255, 255, 255))

        if result.multi_hand_landmarks:
            for hand_landmarks in result.multi_hand_landmarks:
                mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                landmark_data = hand_landmarks
            frame = put_korean_text(frame, '✅ 손 감지됨!', (10, 85), font_size=22, color=(0, 255, 0))
        else:
            frame = put_korean_text(frame, '❌ 손이 감지되지 않습니다', (10, 85), font_size=22, color=(255, 0, 0))

        cv2.imshow('Landmark Capture', frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord(' ') and landmark_data:
            landmarks_list = []
            for idx, lm in enumerate(landmark_data.landmark):
                landmarks_list.append({
                    'id': idx,
                    'x': round(lm.x, 4),
                    'y': round(lm.y, 4),
                    'z': round(lm.z, 4)
                })
            data = {
                'sign_name': sign_name,
                'category': category,
                'hand': 'right',
                'landmarks': landmarks_list
            }
            filename = f"gesture_data/{sign_name}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ Saved: {filename}")
            cap.release()
            cv2.destroyAllWindows()
            return True

        elif key == ord('q'):
            print("❌ Cancelled")
            break

    cap.release()
    cv2.destroyAllWindows()
    return False

# ── MAIN ──
if __name__ == '__main__':
    print("=== Landmark Capture Tool ===\n")

    signs_to_capture = [
        ('안녕하세요', '인사'),
        ('감사합니다', '인사'),
        ('A', '지문자'),
        ('B', '지문자'),
        ('1', '숫자'),
    ]

    for sign_name, category in signs_to_capture:
        print(f"\n→ Next sign: {sign_name} ({category})")
        input("Press ENTER when ready...")
        success = capture_landmark(sign_name, category)
        if success:
            print(f"✅ {sign_name} captured!")
        else:
            print(f"⏭ Skipped {sign_name}")

    print("\n=== All done! ===")