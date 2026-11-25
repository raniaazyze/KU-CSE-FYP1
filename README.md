# Sign Language Learning and Gesture Recognition Platform

A web-based sign language learning system (Konkuk University final-year project). Users learn signs from reference images/videos, then practise in front of a webcam. The system extracts hand landmarks with MediaPipe, compares them with stored reference data, and replies **correct** or **try again**.

Goal: make sign language learning more accessible and ease communication between hearing and deaf people.

## Features

- **Learning mode** – choose a sign and study it from its reference image or video.
- **Exercise mode** – sign in front of the webcam; the app scores your hand shape against the reference and gives feedback. Repeat until it passes.
- **Static signs** – scored from 10 finger-joint angles. The reference is the mean of 5 captures, the pass threshold is 70, and some signs have extra shape checks (for example B, 3, 6, and the thumb–index contact check for F).
- **Moving signs (prototype)** – compared with Dynamic Time Warping (DTW) on the `dtw-prototype` branch; not merged into `main` yet.
- **Admin page** – add, update and delete lessons and categories.
- **Planned UI languages:** English, Malay, Korean.

## Tech stack

Python, Flask, MediaPipe Hands, OpenCV, MySQL, plain HTML/JS frontend.

## Setup

1. Clone the repo and create a virtual environment:
   ```bash
   python -m venv venv
   source venv/Scripts/activate      # Windows (Git Bash); on macOS/Linux: source venv/bin/activate
   pip install -r requirements.txt
   ```
   Versions are pinned (`opencv-contrib-python==4.11.0.86`, `numpy==1.26.4`, `mediapipe==0.10.21`). Please do not upgrade them.
2. Create a MySQL database named `sueo_platform` and load the schema from `db.sql`.
3. Copy `config.example.py` to `config.py` and fill in your database credentials. Do not commit `config.py`.
4. Run the app and open the address it prints:
   ```bash
   python app.py
   ```
   **Restart the app after every branch switch or change to `recognition/static_profiles.json`**, otherwise an old process may keep serving the old scoring.

## Project structure

| Path | Purpose |
|---|---|
| `app.py` | Flask server and API endpoints |
| `sign_language_platform_v2.html`, `static/` | Frontend and experiment pages |
| `gesture_utils.py` | Landmark validation, joint angles and comparison methods |
| `static_recognition.py` | Per-lesson scoring using profiles |
| `recognition/static_profiles.json` | Per-lesson recognition profiles (enabled, sign name, reference angles, threshold, extra checks) |
| `tools/make_profile.py` | Builds a profile from a reference-experiment JSON export |
| `tools/lesson_transfer.py` | Exports and imports lessons between laptops |
| `shared_lessons/` | Exported lesson JSON files shared through git |
| `test_tip_contact.py` | Tests for the thumb–index contact check |
| `experiments/data` | Experiment data |

## Adding a new sign

A lesson only gets the improved scoring if it has an enabled profile in `recognition/static_profiles.json`. Without one, the app falls back to the old lenient method.

1. Add the lesson in the admin page.
2. Open `static/reference_experiment_multi.html`, capture 5 references plus correct and wrong test poses, and export the JSON.
3. Preview the profile, then write it:
   ```bash
   python tools/make_profile.py path/to/lesson-XX_experiment.json
   python tools/make_profile.py path/to/lesson-XX_experiment.json --apply
   ```
   Add `--tip-contact thumb-index` for signs where thumb and index tips must touch (like F).
4. Restart the app and test correct and wrong poses.

## Sharing lessons between laptops

Each laptop has its own database, and git does not carry database rows. Use the transfer tool:

```bash
# on the laptop that made the lesson
python tools/lesson_transfer.py export --lesson-ids 23 --language ASL
git add shared_lessons && git commit && git push

# on the other laptop, after git pull
python tools/lesson_transfer.py import --files shared_lessons/<file>.json          # preview
python tools/lesson_transfer.py import --files shared_lessons/<file>.json --apply  # write
```

## Tests

```bash
python -m unittest test_tip_contact
```

## Known limitations

- Results so far come from small development datasets; thresholds are provisional and need testing with more people and both hands.
- DTW handles speed differences only, not size, position or camera angle.
- Not every sign has a profile yet (C, D, E and G–Z are pending).

## Team

Rujhan and Rania, Konkuk University.
