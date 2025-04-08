# ✅ 위쪽 전역 import에는 serial 절대 쓰지 마세요!
from flask import Flask, request, jsonify
from flask_cors import CORS
import csv, os, random, difflib, io, time
from PIL import Image
import pytesseract
from datetime import datetime
import requests

# ✅ 환경 구분
is_local = os.environ.get("IS_LOCAL", "0") == "1"

if is_local:
    try:
        import serial
        arduino = serial.Serial('COM3', 9600)
    except:
        arduino = None
else:
    arduino = None


app = Flask(__name__)
CORS(app)

DATA_FOLDER = "data"
ATTEMPT_FILE = os.path.join(DATA_FOLDER, "attempts.csv")
CATEGORY_MAP = {
    "사랑": "sarang",
    "분노": "bunno",
    "감사": "gamsa",
    "힘듦": "himdeum",
    "두려움": "duryeoum",
    "결정": "gyeoljeong",
    "용서": "yongseo",
    "믿음": "mideum",
    "위인": "wiin",
    "과학": "gwahak",
    "명언": "myeongeon"
}

# ✅ ngrok 주소를 저장할 변수
global CURRENT_NGROK_URL
CURRENT_NGROK_URL = ""

@app.route('/update-ngrok', methods=['POST'])
def update_ngrok():
    global CURRENT_NGROK_URL
    CURRENT_NGROK_URL = request.form.get("ngrok_url")
    print("[📡 ngrok 등록 완료] ", CURRENT_NGROK_URL)
    return jsonify({"status": "ok", "url": CURRENT_NGROK_URL})

def notify_arduino():
    global CURRENT_NGROK_URL
    if not CURRENT_NGROK_URL:
        print("❌ ngrok 주소가 설정되지 않았습니다.")
        return
    try:
        requests.post(f"{CURRENT_NGROK_URL}/activate-arduino")
        print("✅ 아두이노 요청 전송 성공!")
    except Exception as e:
        print("❌ 아두이노 요청 실패:", e)


def get_today():
    return datetime.now().strftime("%Y-%m-%d")

def get_today_attempts(student_id):
    if not os.path.exists(ATTEMPT_FILE):
        return 0
    with open(ATTEMPT_FILE, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['student_id'] == student_id and row['date'] == get_today():
                return int(row['attempts'])
    return 0

def increment_attempt(student_id):
    rows = []
    found = False
    today = get_today()

    if os.path.exists(ATTEMPT_FILE):
        with open(ATTEMPT_FILE, encoding='utf-8') as f:
            rows = list(csv.DictReader(f))

    for row in rows:
        if row['student_id'] == student_id and row['date'] == today:
            row['attempts'] = str(int(row['attempts']) + 1)
            found = True

    if not found:
        rows.append({'student_id': student_id, 'date': today, 'attempts': '1'})

    with open(ATTEMPT_FILE, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['student_id', 'date', 'attempts'])
        writer.writeheader()
        writer.writerows(rows)

@app.route('/login', methods=['POST'])
def login():
    student_id = request.form.get("student_id")
    password = request.form.get("password")
    user_file = os.path.join(DATA_FOLDER, "users.csv")

    if not os.path.exists(user_file):
        return jsonify({"status": "fail", "message": "회원 데이터가 없습니다."})

    if get_today_attempts(student_id) >= 2:
        return jsonify({"status": "fail", "message": "오늘의 퀴즈 기회를 모두 사용했습니다. 내일 다시 시도해 주세요."})

    with open(user_file, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["student_id"] == student_id and row["password"] == password:
                return jsonify({"status": "success"})

    return jsonify({"status": "fail", "message": "일치하는 회원이 없습니다."})

@app.route('/signup', methods=['POST'])
def signup():
    student_id = request.form.get("student_id")
    password = request.form.get("password")
    user_file = os.path.join(DATA_FOLDER, "users.csv")
    os.makedirs(DATA_FOLDER, exist_ok=True)

    if not os.path.exists(user_file):
        with open(user_file, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=["student_id", "password"])
            writer.writeheader()

    with open(user_file, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["student_id"] == student_id:
                return jsonify({"status": "fail", "message": "이미 존재하는 학번입니다."})

    with open(user_file, mode='a', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["student_id", "password"])
        writer.writerow({"student_id": student_id, "password": password})

    return jsonify({"status": "success"})

@app.route('/quiz')
def get_quiz():
    category = request.args.get("category")
    filename = CATEGORY_MAP.get(category, category) + ".csv"
    filepath = os.path.join(DATA_FOLDER, filename)

    if not os.path.exists(filepath):
        return jsonify({"error": f"'{category}'에 해당하는 퀴즈 파일이 없습니다."}), 404

    try:
        with open(filepath, encoding='utf-8') as f:
            reader = list(csv.DictReader(f))
            if not reader:
                return jsonify({"error": "퀴즈 항목이 비어 있습니다."}), 400
            quiz = random.choice(reader)
            return jsonify(quiz)
    except Exception as e:
        return jsonify({"error": f"퀴즈를 불러오는데 실패했습니다: {str(e)}"}), 500

@app.route('/quiz-fail', methods=['POST'])
def quiz_fail():
    student_id = request.form.get("student_id")
    if not student_id:
        return jsonify({"status": "fail", "message": "학번 누락"})
    increment_attempt(student_id)
    return jsonify({"status": "success"})

@app.route('/today')
def get_today_quote():
    filepath = os.path.join(DATA_FOLDER, "quotes.csv")
    if not os.path.exists(filepath):
        return jsonify({"error": "명언 데이터 파일이 없습니다."}), 404
    try:
        with open(filepath, encoding='utf-8') as f:
            reader = list(csv.DictReader(f))
            if not reader:
                return jsonify({"error": "명언이 비어 있습니다."}), 400
            quote = random.choice(reader)
            return jsonify(quote)
    except Exception as e:
        return jsonify({"error": f"명언을 불러오는데 실패했습니다: {str(e)}"}), 500

@app.route('/submit-writing', methods=['POST'])
def check_handwriting():
    student_id = request.form.get("student_id")
    target_text = request.form.get("target_text")
    image_file = request.files.get("image")

    if not student_id or not image_file or not target_text:
        return jsonify({"status": "fail", "message": "데이터가 부족합니다."}), 400

    image = Image.open(image_file.stream).convert("L")
    custom_config = r'--oem 3 --psm 6'
    extracted_text = pytesseract.image_to_string(image, lang='kor', config=custom_config)

    similarity = difflib.SequenceMatcher(None, target_text.strip(), extracted_text.strip()).ratio()
    print(f"📝 OCR 결과: {extracted_text.strip()} / 🎯 목표: {target_text.strip()} / 📊 유사도: {similarity:.2f}")

    if similarity >= 0.7:
        notify_arduino()
        return jsonify({"status": "success", "message": "성공적으로 작성했습니다!"})
    else:
        return jsonify({"status": "fail", "message": "다시 시도해주세요."})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
