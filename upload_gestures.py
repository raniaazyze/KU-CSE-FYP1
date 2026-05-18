import json
import os
import requests

API = 'http://127.0.0.1:5000/api'

# Map sign names to lesson IDs from your database
# Check your MySQL LESSONS table for the correct IDs
sign_to_lesson = {
    'A': 1,
    'B': 2,
    '1': 3,
    '안녕하세요': 4,
    '밥': 5
}

def upload_gesture(sign_name, lesson_id):
    filename = f"gesture_data/{sign_name}.json"
    if not os.path.exists(filename):
        print(f"❌ File not found: {filename}")
        return False
    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)
    landmark_json = json.dumps(data, ensure_ascii=False)
    res = requests.post(f"{API}/gesture", json={
        'lesson_id': lesson_id,
        'landmark_json': landmark_json  
    })
    if res.status_code == 201:
        print(f"✅ Uploaded: {sign_name} → lesson_id {lesson_id}")
        return True
    else:
        print(f"❌ Failed: {sign_name} — {res.json()}")
        return False

if __name__ == '__main__':
    # print("=== Uploading Gesture Data to MySQL ===\n")
    # for sign_name, lesson_id in sign_to_lesson.items():
    #     upload_gesture(sign_name, lesson_id)
    # print("\n=== Upload Complete! ===")
    
    upload_gesture('밥', 5)
    print("\n=== Done! ===")