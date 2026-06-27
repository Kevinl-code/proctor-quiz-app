from flask import Flask, render_template, request, redirect, flash, jsonify, session, send_file, send_from_directory, url_for
from pymongo import MongoClient
from authlib.integrations.flask_client import OAuth
import re, os, io, qrcode, docx, requests, uuid, pdfplumber
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO 
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from PIL import Image, ImageDraw
from qrcode.constants import ERROR_CORRECT_H
import telegram
import threading

BASE_URL = os.getenv("BASE_URL", "https://pqds.onrender.com")
print("🚀 NEW CODE DEPLOYED - BASE_URL FIX ACTIVE")

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client['proctor']
BOT_TOKEN = os.getenv("BOT_TOKEN")
SECRET_KEY = os.getenv("SECRET_KEY", "fallback_secret")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# 👇 ADD THESE SMTP CONFIGURATIONS RIGHT HERE 👇
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER")  # Your email address
SMTP_PASS = os.getenv("SMTP_PASS")  # Your 16-character App Password
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "kevinlazarus03@gmail.com") # Fallback admin email if needed

app = Flask(__name__)
app.secret_key = SECRET_KEY

oauth = OAuth(app)

google = oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile"
    }
)

# ================= DATABASE =================
users_collection = db['users']
quiz = db["quizzes"]
questions = db["questions"]
activity = db["student_activity"]
scores = db["scores"]
submissions = db["submissions"]
telegram_sessions = db["telegram_sessions"]

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ================= TELEGRAM UTILS =================
def tg(method, payload):
    return requests.post(f"{TELEGRAM_API}/{method}", json=payload, timeout=20)

def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    tg("sendMessage", payload)

def send_photo(chat_id, photo_bytes, caption=None):
    files = {"photo": ("qr.png", photo_bytes)}
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
    requests.post(f"{TELEGRAM_API}/sendPhoto", data=data, files=files, timeout=30)

# ================= HOME & UTILS =================
@app.route('/')
def spinner():
    return render_template('spinner.html')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static/images'),
                               'favicon.png', mimetype='image/vnd.microsoft.icon')

# ================= AUTH =================
teacher_pattern = re.compile(r'^[a-z0-9]+@bhc\.professor\.com$')
student_pattern = re.compile(r'^[a-z0-9]+@bhc\.student\.com$')

@app.route("/google-login")
def google_login():
    redirect_uri = url_for("google_authorize", _external=True)
    return google.authorize_redirect(redirect_uri)
    
@app.route("/google-authorize")
def google_authorize():
    token = google.authorize_access_token()
    user_info = token.get("userinfo")
    email = user_info["email"]

    user = users_collection.find_one({"email": email})

    if not user:
        session["google_user"] = {
            "name": user_info["name"],
            "email": user_info["email"],
            "picture": user_info.get("picture")
        }
        return redirect("/select-role")

    session["user"] = user["email"]
    session["name"] = user["name"]

    if user["role"] == "professor":
        return redirect("/admin")

    return redirect("/student")
    
@app.route("/select-role")
def select_role():
    if "google_user" not in session:
        return redirect("/login")
    return render_template("select_role.html")

@app.route("/save-role", methods=["POST"])
def save_role():
    if "google_user" not in session:
        return redirect("/login")

    role = request.form["role"]
    user_data = session["google_user"]

    users_collection.insert_one({
        "name": user_data["name"],
        "email": user_data["email"],
        "picture": user_data.get("picture"),
        "role": role,
        "google_login": True,
        "created_at": datetime.now()
    })

    session["user"] = user_data["email"]
    session["name"] = user_data["name"]
    session.pop("google_user")

    if role == "professor":
        return redirect("/admin")

    return redirect("/student")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = users_collection.find_one({"email":email,"password":password})
        if user:
            session["user"] = email
            session["name"] = user["name"]

            if teacher_pattern.match(email):
                return redirect("/admin")
            elif student_pattern.match(email):
                return redirect("/student")

        flash("Invalid credentials")
        return redirect("/login")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/signup",methods=["GET","POST"])
def signup():
    if request.method == "POST":
        users_collection.insert_one({
            "name":request.form["name"],
            "email":request.form["email"],
            "password":request.form["password"],
            "role":request.form["role"]
        })
        flash("Account Created Successfully")
        return redirect("/login")

    return render_template("signup.html")

# ================= DASHBOARDS =================
@app.route("/admin")
def admin_dashboard():
    if "user" not in session:
        return redirect("/login")
    return render_template("admin_dashboard.html")

@app.route("/student")
def student_dashboard():
    if "user" not in session:
        return redirect("/login")
    return render_template("student_dashboard.html")

# ================= CREATE QUIZ (MANUAL MANUAL DATA) =================
@app.route("/create_quiz",methods=["POST"])
def create_quiz():
    data = request.json
    quiz_id = str(uuid.uuid4())[:8]

    start_time = datetime.fromisoformat(data["start"])
    duration = int(data["duration"])
    end_time = start_time + timedelta(minutes=duration)

    quiz.insert_one({
        "quiz_id":quiz_id,
        "title":data["title"],
        "start_time":start_time.isoformat(),
        "end_time":end_time.isoformat(),
        "duration":duration,
        "created_at":datetime.now()
    })

    for q in data.get("questions",[]):
        questions.insert_one({
            "quiz_id":quiz_id,
            "question":q["question"],
            "options":q["options"],
            "answer":q["answer"]
        })

    return jsonify({"msg":"Quiz Created","quiz_id":quiz_id})

# ================= FILE UPLOAD (WEB PORTAL) =================
@app.route("/upload_quiz_file", methods=["POST"])
def upload_quiz_file():
    """
    Reads metadata and files submitted via web form, processes 
    the file identical to the Telegram method, and stores it in MongoDB.
    """
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    if "file" not in request.files:
        return jsonify({"error": "No file chunk found"}), 400

    file = request.files["file"]
    title = request.form.get("title", "Untitled Quiz")
    duration = int(request.form.get("duration", 30))
    start_str = request.form.get("start")  # Format expected: YYYY-MM-DDTHH:MM

    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # Extract parsing using your memory buffer method
        memory_file = BytesIO(file.read())
        parsed_questions = extract_questions_from_file(memory_file, file.filename.lower())

        if not parsed_questions:
            return jsonify({"error": "No valid questions could be parsed from the file structure."}), 400

        # Structural scheduling updates
        quiz_id = str(uuid.uuid4())[:8]
        start_time = datetime.fromisoformat(start_str) if start_str else datetime.now()
        end_time = start_time + timedelta(minutes=duration)

        # Write to core collections
        quiz.insert_one({
            "quiz_id": quiz_id,
            "title": title,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration": duration,
            "created_at": datetime.now()
        })

        for q in parsed_questions:
            questions.insert_one({
                "quiz_id": quiz_id,
                "question": q["question"],
                "options": q["options"],
                "answer": q["answer"]
            })

        return jsonify({"msg": "Quiz securely compiled via file upload!", "quiz_id": quiz_id})

    except Exception as e:
        return jsonify({"error": f"Failed to execute parsing operations: {str(e)}"}), 500

@app.route("/upload_questions", methods=["POST"])
def upload_questions():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    if "file" not in request.files:
        return jsonify({"error": "No file chunk found"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        memory_file = BytesIO(file.read())
        parsed_questions = extract_questions_from_file(memory_file, file.filename.lower())

        if not parsed_questions:
            return jsonify({"error": "No valid questions could be parsed from the file structure."}), 400

        return jsonify(parsed_questions)

    except Exception as e:
        return jsonify({"error": f"Failed to execute parsing operations: {str(e)}"}), 500

# ================= FILE PARSER MECHANISM =================
def extract_questions_from_file(file, filename):
    parsed = []
    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(file)
            # Strip whitespace from column names and convert to lowercase
            df.columns = [str(col).strip().lower() for col in df.columns]
            
            # Helper to find a column name matching aliases
            def get_col_value(row, aliases):
                for alias in aliases:
                    if alias in df.columns:
                        return str(row[alias]).strip()
                return ""

            for _, r in df.iterrows():
                q_text = get_col_value(r, ["question", "q", "questions", "text"])
                opt_a = get_col_value(r, ["a", "option a", "option_a"])
                opt_b = get_col_value(r, ["b", "option b", "option_b"])
                opt_c = get_col_value(r, ["c", "option c", "option_c"])
                opt_d = get_col_value(r, ["d", "option d", "option_d"])
                ans_val = get_col_value(r, ["answer", "ans", "correct", "correct_answer"])
                
                if q_text and opt_a and opt_b and opt_c and opt_d and ans_val:
                    # Resolve answer letter
                    ans_val_upper = ans_val.upper()
                    final_ans = ""
                    if ans_val_upper in ["A", "B", "C", "D"]:
                        final_ans = ans_val_upper
                    else:
                        # Check if the answer text matches any option value
                        opts = [opt_a, opt_b, opt_c, opt_d]
                        for idx, opt in enumerate(opts):
                            if opt.lower() == ans_val.lower():
                                letters = ["A", "B", "C", "D"]
                                final_ans = letters[idx]
                                break
                    if final_ans:
                        parsed.append({
                            "question": q_text,
                            "options": [opt_a, opt_b, opt_c, opt_d],
                            "answer": final_ans
                        })
        elif filename.endswith(".txt"):
            lines = file.read().decode("utf-8", errors="ignore").splitlines()
            parsed.extend(parse_block_questions(lines))
        elif filename.endswith(".docx"):
            doc = docx.Document(file)
            lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            parsed.extend(parse_block_questions(lines))
        elif filename.endswith(".pdf"):
            with pdfplumber.open(file) as pdf:
                lines = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        lines.extend(text.splitlines())
            parsed.extend(parse_block_questions(lines))
    except Exception as e:
        print(f"Error in extract_questions_from_file: {str(e)}")
        raise e
    return parsed

def finalize_question(q):
    # Resolve answer if answer_text is present
    if not q.get("answer") and q.get("answer_text"):
        ans_text = q["answer_text"].strip().lower()
        # Try to find which option matches ans_text
        for idx, opt in enumerate(q["options"]):
            if opt.strip().lower() == ans_text:
                letters = ["A", "B", "C", "D"]
                if idx < len(letters):
                    q["answer"] = letters[idx]
                    break
    
    # Clean up options (make sure there are exactly 4 options)
    if len(q["options"]) == 4 and q.get("answer") in ["A", "B", "C", "D"]:
        return {
            "question": q["question"],
            "options": q["options"],
            "answer": q["answer"]
        }
    return None

def parse_block_questions(lines):
    result = []
    current = None
    
    option_pattern = re.compile(r'^\s*([A-D])\s*[\.\)]\s*(.*)$', re.IGNORECASE)
    # Identify answer lines: starts with ans/answer/correct answer, followed by delimiter, then the answer
    answer_indicator_pattern = re.compile(r'^\s*(?:correct\s+)?ans(?:wer)?\s*[\:\-\s]\s*(.*)$', re.IGNORECASE)

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        # Check if it's an answer line
        ans_indicator_match = answer_indicator_pattern.match(line_str)
        if ans_indicator_match:
            if current:
                ans_val = ans_indicator_match.group(1).strip().upper()
                # Extract letter if it starts with A/B/C/D
                letter_match = re.match(r'^([A-D])(?:\b|[\.\)\s]|$)', ans_val)
                if letter_match:
                    current["answer"] = letter_match.group(1)
                else:
                    # Save raw answer text to match against options later
                    current["answer_text"] = ans_val
            continue

        # Check if it's an option
        opt_match = option_pattern.match(line_str)
        if opt_match:
            if current:
                current["options"].append(opt_match.group(2).strip())
            continue

        # Otherwise, it's a question text line
        # Decide if we start a new question
        is_new_q = False
        q_text = line_str

        # If it has a number prefix, e.g. "1. " or "Q1: " or "1) "
        q_prefix_match = re.match(r'^\s*(?:q(?:uestion)?\s*)?\d+\s*[\.\)]\s*(.*)$', line_str, re.IGNORECASE)
        if q_prefix_match:
            is_new_q = True
            q_text = q_prefix_match.group(1).strip()
        elif "?" in line_str:
            if current is None or len(current["options"]) > 0 or current.get("answer") or current.get("answer_text"):
                is_new_q = True
        elif current is not None and (len(current["options"]) > 0 or current.get("answer") or current.get("answer_text")):
            is_new_q = True

        if is_new_q or current is None:
            if current:
                # Finalize current question before starting new
                finalized = finalize_question(current)
                if finalized:
                    result.append(finalized)
            current = {"question": q_text, "options": [], "answer": ""}
        else:
            if len(current["options"]) == 0:
                current["question"] += " " + line_str

    if current:
        finalized = finalize_question(current)
        if finalized:
            result.append(finalized)

    return result

# ================= QR & ATTEMPTS =================
@app.route("/quiz_info/<quiz_id>")
def quiz_info(quiz_id):
    if "user" not in session:
        return redirect("/login")

    email = session.get("user")
    if teacher_pattern.match(email):
        return redirect("/admin")

    q = quiz.find_one({"quiz_id": quiz_id}, {"_id":0})
    return render_template("quiz_info.html", quiz=q)

@app.route("/join/<quiz_id>")
def join_quiz(quiz_id):
    user = session.get("user")
    if not user:
        return redirect("/login")
    if teacher_pattern.match(user):
        return redirect("/admin")
    return redirect(f"/quiz/{quiz_id}")
    
@app.route("/quiz/<quiz_id>")
def attend_quiz(quiz_id):
    if "user" not in session:
        return redirect("/login")
    return render_template("student_quiz.html")

# ================= DATA ENDPOINTS =================
@app.route("/get_quizzes")
def get_quizzes():
    quizzes = list(quiz.find({}, {"_id":0}))
    student_id = session.get("user")

    for q in quizzes:
        attempt = submissions.find_one({
            "quiz_id": q["quiz_id"],
            "student_id": student_id
        })
        q["attempted"] = True if attempt else False
    return jsonify(quizzes)

@app.route("/check_attempt/<quiz_id>")
def check_attempt(quiz_id):
    student_id = session.get("user")
    existing = submissions.find_one({
        "quiz_id": quiz_id,
        "student_id": student_id
    })
    return jsonify({"attempted": True if existing else False})

@app.route("/get_quiz/<quiz_id>")
def get_quiz(quiz_id):
    q = quiz.find_one({"quiz_id":quiz_id},{"_id":0})
    return jsonify(q)

@app.route("/get_questions/<quiz_id>")
def get_questions(quiz_id):
    q = list(questions.find({"quiz_id":quiz_id},{"_id":0}))
    return jsonify(q)

@app.route("/submit_quiz",methods=["POST"])
def submit_quiz():
    data = request.json
    student_id = session.get("user")

    existing = submissions.find_one({
        "quiz_id": data["quiz_id"],
        "student_id": student_id
    })
    if existing:
        return jsonify({"msg":"Already submitted"})

    name = session.get("name")
    submissions.insert_one({
        "quiz_id": data["quiz_id"],
        "student_id": student_id,
        "name": name,
        "correct":data["correct"],
        "wrong":data["wrong"],
        "skipped":data["skipped"]
    })

    scores.insert_one({
        "quiz_id": data["quiz_id"],
        "student_id": student_id,
        "name": name,
        "correct":data["correct"],
        "wrong":data["wrong"],
        "skipped":data["skipped"],
        "result":"completed"
    })

    activity.insert_one({
        "quiz_id": data["quiz_id"],
        "student_id": student_id,
        "name": name,
        "question_answered": data["correct"] + data["wrong"],
        "correct": data["correct"],
        "wrong": data["wrong"],
        "skipped": data["skipped"],
        "violation_type": ", ".join([v["type"] for v in data.get("violations",[])]),
        "violation_count": len(data.get("violations",[])),
        "timestamp": datetime.now()
    })
    return jsonify({"msg":"submitted successfully"})

@app.route("/get_activity")
def get_activity():
    data = list(activity.find({},{"_id":0}))
    return jsonify(data)

@app.route("/get_scores")
def get_scores():
    data = list(scores.find({},{"_id":0}))
    data = sorted(data,key=lambda x:x["correct"],reverse=True)

    for i,x in enumerate(data):
        if i==0: x["badge"]="🥇"
        elif i==1: x["badge"]="🥈"
        elif i==2: x["badge"]="🥉"
        else: x["badge"]="Bronze"
    return jsonify(data)


def generate_styled_qr_card(quiz_id, title, duration, base_url):

    url = f"{base_url}/join/{quiz_id}"

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=10,
        border=2
    )

    qr.add_data(url)
    qr.make(fit=True)

    qr_img = qr.make_image(
        fill_color="#111827",
        back_color="white"
    ).convert("RGBA").resize((200, 200))

    # logo (safe fail)
    try:
        logo = Image.open("static/images/logo.png").convert("RGBA")
        logo_size = 50
        logo = logo.resize((logo_size, logo_size))

        pos = (
            qr_img.size[0]//2 - logo_size//2,
            qr_img.size[1]//2 - logo_size//2
        )

        circle = Image.new("RGBA", (logo_size+10, logo_size+10), (255,255,255,255))
        mask = Image.new("L", circle.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0,0,circle.size[0],circle.size[1]), fill=255)

        qr_img.paste(circle, (pos[0]-5, pos[1]-5), mask)
        qr_img.paste(logo, pos, logo)

    except:
        pass

    card = Image.new("RGBA", (300, 380), (0,0,0,0))
    draw = ImageDraw.Draw(card)

    for i in range(380):
        r = int(102 + (118-102)*(i/380))
        g = int(126 + (75-126)*(i/380))
        b = int(234 + (162-234)*(i/380))
        draw.line([(0,i),(300,i)], fill=(r,g,b))

    mask = Image.new("L", (300,380), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle((0,0,300,380), radius=25, fill=255)
    card.putalpha(mask)

    card.paste(qr_img, (50, 100), qr_img)

    try:
        from PIL import ImageFont
        font_title = ImageFont.truetype("arial.ttf", 18)
        font_small = ImageFont.truetype("arial.ttf", 12)
    except:
        font_title = None
        font_small = None

    draw = ImageDraw.Draw(card)

    draw.text((90, 20), f"Quiz ID: {quiz_id}", fill="white", font=font_small)
    draw.text((70, 45), title[:20], fill="white", font=font_title)
    draw.text((60, 70), f"Duration: {duration} mins", fill="white", font=font_small)
    draw.text((80, 320), "Scan to Join", fill="white", font=font_small)

    img_io = BytesIO()
    card.save(img_io, format="PNG")
    img_io.seek(0)

    return img_io

# ================= TELEGRAM KEYBOARDS =================

def main_menu_kb():
    return {
        "inline_keyboard": [
            [{"text": "➕ Create Quiz", "callback_data": "create"}],
            [{"text": "📊 Dashboard", "url": request.host_url}],
            [{"text": "❓ Help", "callback_data": "help"}]
        ]
    }


def confirm_kb():
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Confirm", "callback_data": "confirm"},
                {"text": "✏ Edit", "callback_data": "edit_current"}
            ]
        ]
    }


def upload_confirm_kb():
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Confirm", "callback_data": "confirm"},
                {"text": "📎 Upload Again", "callback_data": "edit_questions"}
            ]
        ]
    }


def summary_kb():
    return {
        "inline_keyboard": [
            [
                {"text": "✏ Title", "callback_data": "edit_title"},
                {"text": "✏ Duration", "callback_data": "edit_duration"}
            ],
            [
                {"text": "✏ Start", "callback_data": "edit_start"},
                {"text": "✏ Questions", "callback_data": "edit_questions"}
            ],
            [
                {"text": "✅ Create Quiz", "callback_data": "final_submit"}
            ],
            [
                {"text": "❌ Cancel", "callback_data": "cancel"}
            ]
        ]
    }


# ================= TELEGRAM STATE =================

def set_step(chat_id, step):
    telegram_sessions.update_one(
        {"chat_id": chat_id},
        {"$set": {"step": step}},
        upsert=True
    )


def get_user(chat_id):
    return telegram_sessions.find_one({"chat_id": chat_id}) or {}


def get_data(chat_id):
    user = get_user(chat_id)
    return user.get("data", {})


# ================= ASK FUNCTIONS =================

def ask_title(chat_id):
    set_step(chat_id, "title")
    send_message(chat_id, "📝 Enter Quiz Title")


def ask_duration(chat_id):
    set_step(chat_id, "duration")
    send_message(chat_id, "⏱ Enter Duration (minutes)")


def ask_start(chat_id):
    set_step(chat_id, "start")
    send_message(
        chat_id,
        "📅 Enter Start Time\n\nFormat:\nYYYY-MM-DD HH:MM"
    )


def ask_upload(chat_id):
    set_step(chat_id, "upload")
    send_message(
        chat_id,
        "📎 Upload Question File\n\nSupported:\nCSV\nTXT\nDOCX\nPDF"
    )


# ================= CONFIRM FUNCTIONS =================

def confirm_title(chat_id):
    data = get_data(chat_id)

    send_message(
        chat_id,
        f"📝 Title\n\n{data['title']}\n\nConfirm?",
        confirm_kb()
    )

    set_step(chat_id, "confirm_title")


def confirm_duration(chat_id):
    data = get_data(chat_id)

    send_message(
        chat_id,
        f"⏱ Duration\n\n{data['duration']} minutes\n\nConfirm?",
        confirm_kb()
    )

    set_step(chat_id, "confirm_duration")


def confirm_start(chat_id):
    data = get_data(chat_id)

    send_message(
        chat_id,
        f"📅 Start Time\n\n{data['start']}\n\nConfirm?",
        confirm_kb()
    )

    set_step(chat_id, "confirm_start")


def confirm_questions(chat_id):

    data = get_data(chat_id)

    send_message(
        chat_id,
        f"📚 Parsed {len(data['questions'])} Questions\n\nConfirm?",
        upload_confirm_kb()
    )

    set_step(chat_id, "confirm_questions")


# ================= SUMMARY =================

def send_summary(chat_id):

    data = get_data(chat_id)

    msg = f"""
📋 QUIZ SUMMARY

📝 Title
{data['title']}

⏱ Duration
{data['duration']} Minutes

📅 Start
{data['start']}

📚 Questions
{len(data['questions'])}
"""

    send_message(
        chat_id,
        msg,
        summary_kb()
    )

    set_step(chat_id, "summary")


# ================= NEXT STEP =================

def next_step(chat_id):

    data = get_data(chat_id)

    if not data.get("title"):
        ask_title(chat_id)
        return

    if not data.get("duration"):
        ask_duration(chat_id)
        return

    if not data.get("start"):
        ask_start(chat_id)
        return

    if not data.get("questions"):
        ask_upload(chat_id)
        return

    send_summary(chat_id)


# ================= EDIT =================

def edit_field(chat_id, field):

    if field == "title":
        ask_title(chat_id)

    elif field == "duration":
        ask_duration(chat_id)

    elif field == "start":
        ask_start(chat_id)

    elif field == "questions":
        ask_upload(chat_id)


# ================= HELP =================

HELP_TEXT = """
🤖 PQDS Quiz Bot

Create quizzes in four simple steps.

1️⃣ Enter Quiz Title

2️⃣ Enter Duration

3️⃣ Enter Start Time

4️⃣ Upload Questions

Supported Files

• CSV
• TXT
• DOCX
• PDF

Question Format

Question?

A. Option A
B. Option B
C. Option C
D. Option D

Answer: B

After uploading you can edit any field before final submission.

Commands

/start - Restart Bot
/help - Show Help
"""

@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    
    update = request.json or {}

    # ================= MESSAGE HANDLER =================
    if "message" in update:

        msg = update["message"]
        chat_id = msg["chat"]["id"]

        user = get_user(chat_id)
        step = user.get("step")
        data = user.get("data", {})

        # -------- TEXT HANDLING --------
        if "text" in msg:
            text = msg["text"].strip()

            # /start
            if text.lower() == "/start":
                telegram_sessions.delete_one({"chat_id": chat_id})
                send_message(chat_id, "🤖 Welcome to Quiz Bot", main_menu_kb())
                return "ok"

            # /help
            if text.lower() == "/help":
                send_message(chat_id, HELP_TEXT, main_menu_kb())
                return "ok"

            # ================= TITLE =================
            if step == "title":
                if len(text) < 3:
                    send_message(chat_id, "⚠️ Title too short. Try again:")
                    return "ok"

                telegram_sessions.update_one(
                    {"chat_id": chat_id},
                    {"$set": {"data.title": text, "step": None}},
                    upsert=True
                )

                confirm_title(chat_id)
                return "ok"

            # ================= DURATION =================
            if step == "duration":
                if not text.isdigit() or int(text) <= 0:
                    send_message(chat_id, "⚠️ Enter valid duration (minutes):")
                    return "ok"

                telegram_sessions.update_one(
                    {"chat_id": chat_id},
                    {"$set": {"data.duration": int(text), "step": None}},
                    upsert=True
                )

                confirm_duration(chat_id)
                return "ok"

            # ================= START TIME =================
            if step == "start":
                try:
                    dt = datetime.strptime(text, "%Y-%m-%d %H:%M")

                    telegram_sessions.update_one(
                        {"chat_id": chat_id},
                        {"$set": {"data.start": dt.isoformat(), "step": None}},
                        upsert=True
                    )

                    confirm_start(chat_id)

                except:
                    send_message(chat_id, "⚠️ Format: YYYY-MM-DD HH:MM")

                return "ok"

        # ================= FILE UPLOAD =================
        if "document" in msg and step == "upload":

            file_id = msg["document"]["file_id"]
            file_name = msg["document"].get("file_name", "file.txt").lower()

            try:
                res = requests.get(
                    f"{TELEGRAM_API}/getFile",
                    params={"file_id": file_id}
                ).json()

                if not res.get("ok"):
                    send_message(chat_id, "❌ File fetch failed")
                    return "ok"

                path = res["result"]["file_path"]
                file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{path}"
                file_data = requests.get(file_url).content

                memory_file = BytesIO(file_data)

                parsed = extract_questions_from_file(memory_file, file_name)

                if not parsed:
                    send_message(chat_id, "⚠️ No valid questions found.")
                    return "ok"

                telegram_sessions.update_one(
                    {"chat_id": chat_id},
                    {"$set": {"data.questions": parsed, "step": None}},
                    upsert=True
                )

                confirm_questions(chat_id)

            except Exception as e:
                send_message(chat_id, f"❌ Error: {str(e)}")

            return "ok"

    # ================= CALLBACK HANDLER =================
    if "callback_query" in update:

        cb = update["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        action = cb["data"]

        requests.post(
            f"{TELEGRAM_API}/answerCallbackQuery",
            json={"callback_query_id": cb["id"]}
        )

        user = get_user(chat_id)
        step = user.get("step")
        data = user.get("data", {})

        # -------- CREATE --------
        if action == "create":
            telegram_sessions.update_one(
                {"chat_id": chat_id},
                {"$set": {"step": "title", "data": {}}},
                upsert=True
            )
            send_message(chat_id, "📝 Enter Quiz Title:")
            return "ok"

        # -------- CONFIRM FLOW --------
        if action == "confirm":

            if step == "confirm_title":
                next_step(chat_id)

            elif step == "confirm_duration":
                next_step(chat_id)

            elif step == "confirm_start":
                next_step(chat_id)

            elif step == "confirm_questions":
                next_step(chat_id)

            elif step == "summary":
                send_message(chat_id, "⚠️ Use 'Create Quiz' button")

            return "ok"

        # -------- FINAL SUBMIT --------
        if action == "final_submit":

            missing = []

            if not data.get("title"):
                missing.append("Title")
            if not data.get("duration"):
                missing.append("Duration")
            if not data.get("start"):
                missing.append("Start Time")
            if not data.get("questions"):
                missing.append("Questions")

            if missing:
                send_message(chat_id, "⚠️ Missing:\n" + "\n".join(missing))
                return "ok"

            try:
                quiz_id = create_quiz_from_session(chat_id, data)

                send_final_quiz(
                    chat_id,
                    quiz_id,
                    data["title"],
                    data["duration"]
                )

            except Exception as e:
                send_message(chat_id, f"❌ Error: {str(e)}")

            return "ok"

        # -------- EDIT CURRENT --------
        if action == "edit_current":

            mapping = {
                "confirm_title": "title",
                "confirm_duration": "duration",
                "confirm_start": "start",
                "confirm_questions": "questions"
            }

            target = mapping.get(step)

            if target:
                edit_field(chat_id, target)

            return "ok"

        # -------- SPECIFIC EDIT --------
        if action == "edit_title":
            edit_field(chat_id, "title")
            return "ok"

        if action == "edit_duration":
            edit_field(chat_id, "duration")
            return "ok"

        if action == "edit_start":
            edit_field(chat_id, "start")
            return "ok"

        if action == "edit_questions":
            edit_field(chat_id, "questions")
            return "ok"

        # -------- CANCEL --------
        if action == "cancel":
            telegram_sessions.delete_one({"chat_id": chat_id})
            send_message(chat_id, "❌ Cancelled", main_menu_kb())
            return "ok"

        # -------- HELP --------
        if action == "help":
            send_message(chat_id, HELP_TEXT, main_menu_kb())
            return "ok"

    return "ok"

@app.route("/generate_qr/<quiz_id>")
def generate_qr(quiz_id):
    BASE_URL = os.getenv("BASE_URL", "https://pqds.onrender.com")
    join_url = f"{BASE_URL}/join/{quiz_id}"


    q = quiz.find_one({"quiz_id": quiz_id}, {"_id": 0})
    if not q:
        return "Quiz not found"

    img = generate_styled_qr_card(
    quiz_id,
    q["title"],
    q["duration"]
)
    return send_file(img, mimetype="image/png")
    

def create_quiz_from_session(chat_id, data):

    quiz_id = str(uuid.uuid4())[:8]

    start_time = datetime.fromisoformat(data["start"])
    duration = int(data["duration"])
    end_time = start_time + timedelta(minutes=duration)

    # -------- INSERT QUIZ --------
    quiz.insert_one({
        "quiz_id": quiz_id,
        "title": data["title"],
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration": duration,
        "created_at": datetime.now()
    })

    # -------- INSERT QUESTIONS --------
    for q in data.get("questions", []):
        questions.insert_one({
            "quiz_id": quiz_id,
            "question": q["question"],
            "options": q["options"],
            "answer": q["answer"]
        })

    return quiz_id

def send_final_quiz(chat_id, quiz_id, title, duration):

    BASE_URL = os.getenv("BASE_URL", "https://pqds.onrender.com")
    join_url = f"{BASE_URL}/join/{quiz_id}"

    img = generate_styled_qr_card(
        quiz_id,
        title,
        duration,
        BASE_URL
    )

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🚀 Join Quiz", "url": join_url}
            ],
            [
                {"text": "📊 Open Dashboard", "url": f"{BASE_URL}"}
            ]
        ]
    }

    send_message(
        chat_id,
        f"✅ Quiz Created!\n\n📝 {title}\n⏱ {duration} mins\n\n🔗 Join instantly below:",
        keyboard
    )

    send_photo(chat_id, img, keyboard)

    telegram_sessions.delete_one({"chat_id": chat_id})
import os
import threading
import requests
from datetime import datetime
from flask import jsonify, request

# =====================================================================
# FUNCTION 1: THE CORE HTTP API BACKGROUND WORKER
# =====================================================================
def send_email_worker_api(payload, headers):
    """
    Executes the synchronous HTTP POST request to Brevo's REST API.
    Runs entirely within a background thread to prevent blocking main execution.
    """
    try:
        url = "https://api.brevo.com/v3/smtp/email"
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code in [200, 201, 202]:
            print("✅ [EMAIL SUCCESS] Disqualification alert transmitted via Brevo HTTP API.")
        else:
            print(f"❌ [EMAIL API ERROR] Brevo rejected payload. Status: {response.status_code} | Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ [EMAIL NETWORK ERROR] Failed to connect to Brevo API endpoints: {str(e)}")
    except Exception as e:
        print(f"❌ [EMAIL CRITICAL FAILURE] Unexpected error in worker thread: {str(e)}")


# =====================================================================
# FUNCTION 2: THE PAYLOAD & LOGISTICS ASSEMBLER
# =====================================================================
def notify_admin_disqualification(student_id, name, quiz_id, violations):
    """
    Constructs the tracking log text and maps the structured JSON payload 
    required by Brevo's API schema, then calls the execution worker.
    """
    brevo_api_key = os.getenv("BREVO_API_KEY") or os.getenv("EMAIL_API_KEY")
    sender_email = os.getenv("SENDER_EMAIL", "analytixfest2k2x@gmail.com")
    professor_emails = ["kevinlazarus03@gmail.com"]

    if not brevo_api_key:
        print("⚠️ [EMAIL CONFIG ERROR] Brevo API token missing from environment setup!")
        return

    # Compile clear text list of historical violations logged in database
    violation_report = ""
    for index, entry in enumerate(violations, 1):
        ts = entry.get("timestamp")
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime) else str(ts)
        violation_report += f"  {index}. Type: {entry.get('type', 'Unknown')} | Severity: {entry.get('severity', 'High')} | Time: {ts_str}\n"

    email_body = f"""Hello Professor,

This is an automated alert from the PQDS Proctoring System.

Student '{name}' (ID: {student_id}) has reached the maximum permitted system infractions during Quiz ID: {quiz_id} and has been officially DISQUALIFIED.

Detailed Violations Logged:
{violation_report}

The student's entry in the structural submissions tables has been updated to 'DISQUALIFIED'.

Best regards,
PQDS Proctor System
"""

    payload = {
        "sender": {"name": "PQDS Proctor System", "email": sender_email},
        "to": [{"email": email} for email in professor_emails],
        "subject": f"🚨 PROCTOR ALERT: Disqualification Triggered - {name}",
        "textContent": email_body
    }

    headers = {
        "accept": "application/json",
        "api-key": brevo_api_key,
        "content-type": "application/json"
    }

    send_email_worker_api(payload, headers)


# =====================================================================
# FUNCTION 3: THE PROCTOR VIOLATION LOGIC PIPELINE
# =====================================================================
def handle_proctor_logging(student_id, quiz_id, name, violation_count, new_violations, disqualified, current_session, db):
    """
    Saves state metrics to MongoDB, verifies thread safety constraints, 
    and handles front-end tracking telemetry data updates safely.
    """
    determined_status = "DISQUALIFIED" if disqualified else "ACTIVE_WARNING"

    # 1. Update status parameters and the computed counter fields in the database
    db.submissions.update_one(
        {"quiz_id": quiz_id, "student_id": student_id},
        {"$set": {
            "name": name,
            "status": determined_status,
            "violation_count": violation_count,
            "timestamp": datetime.now()
        }},
        upsert=True
    )
    
    # 2. Append the descriptive metadata logs into the database profile array
    if new_violations:
        # Normalize timestamps for new entries
        for v in new_violations:
            if "timestamp" not in v:
                v["timestamp"] = datetime.now()
                
        db.submissions.update_one(
            {"quiz_id": quiz_id, "student_id": student_id},
            {"$push": {"history_logs": {"$each": new_violations}}}
        )
    
    # 3. Only invoke the asynchronous administrative worker if the validation state triggers a lockout
    if disqualified and current_session and not current_session.get("email_sent", False):
        db.proctor_sessions.update_one(
            {"_id": current_session["_id"]},
            {"$set": {"email_sent": True}}
        )
        
        # Retrieve complete historical log entries from database to populate a comprehensive report
        updated_record = db.submissions.find_one({"quiz_id": quiz_id, "student_id": student_id})
        complete_history = updated_record.get("history_logs", new_violations) if updated_record else new_violations
        
        email_thread = threading.Thread(
            target=notify_admin_disqualification, 
            args=(student_id, name, quiz_id, complete_history)
        )
        email_thread.daemon = True
        email_thread.start()
        
        print(f"⚡ [PROCTOR] Offloaded background tracking pipeline successfully for disqualified student {name}.")
    
    # 4. Generate system state response codes back to front-end engine structures
    return jsonify({
        "status": "logged", 
        "disqualified": disqualified,
        "violation_count": violation_count,
        "message": "Disqualified." if disqualified else f"{violation_count}/2 violations committed. Next one will disqualify you."
    })



@app.route('/log_violation', methods=['POST'])
def log_violation_route():
    data = request.json or {}
    
    student_id = data.get("student_id")
    quiz_id = data.get("quiz_id")
    name = data.get("name")
    new_violations = data.get("violations", [])
    
    if not student_id or not quiz_id:
        return jsonify({"status": "error", "message": "Missing validation requirements."}), 400

    # ─── BACKEND AUTO-INCREMENT LOGIC ───
    # Look up what the database actually has on file for this student right now
    existing_submission = db.submissions.find_one({"quiz_id": quiz_id, "student_id": student_id})
    prior_count = existing_submission.get("violation_count", 0) if existing_submission else 0
    
    # Auto-increment the count on the backend safely
    violation_count = prior_count + 1
    
    # Rule definition: if they hit 2 or more violations, they are instantly disqualified
    disqualified = violation_count >= 2
    
    # Fetch background matching context tracking logs safely
    current_session = db.proctor_sessions.find_one({"student_id": student_id, "quiz_id": quiz_id})
    
    # Fire off execution tracking updates
    return handle_proctor_logging(
        student_id, quiz_id, name, violation_count, new_violations, disqualified, current_session, db
    )    

@app.route("/privacy")
def privacy():
    return """
    <html>
    <head><title>PQDS Privacy Policy</title></head>
    <body style="font-family: Arial; padding: 40px; line-height: 1.6; max-width: 800px; margin: auto;">
        <h1>PQDS Privacy Policy</h1>
        <p>PQDS Quiz Bot collects only necessary data such as quiz details, questions uploaded, student scores, and activity logs.</p>
        <p>We do NOT sell or share your data with third parties.</p>
        <email>kevinlazarus03@gmail.com</email>
    </body>
    </html>
    """

if __name__ == "__main__":
    app.run(debug=True)
