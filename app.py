from flask import Flask, render_template, request, redirect, flash, jsonify, session, send_file, send_from_directory
from pymongo import MongoClient
import re, os, io, qrcode, docx, requests, uuid, pdfplumber
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO 
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from PIL import Image, ImageDraw
from qrcode.constants import ERROR_CORRECT_H
import telegram
#from telegram import Bot

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client['proctor']
BOT_TOKEN = os.getenv("BOT_TOKEN")
SECRET_KEY = os.getenv("SECRET_KEY", "fallback_secret")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
#bot = Bot(token=BOT_TOKEN)



app = Flask(__name__)
app.secret_key = SECRET_KEY

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

# ================= TELEGRAM =================

def send_message(chat_id, text):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })

# ================= HOME =================
@app.route('/')
def spinner():
    return render_template('spinner.html')

# ================= AUTH =================
teacher_pattern = re.compile(r'^[a-z0-9]+@bhc\.professor\.com$')
student_pattern = re.compile(r'^[a-z0-9]+@bhc\.student\.com$')

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

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static/images'),
                               'favicon.png', mimetype='image/vnd.microsoft.icon')

# ================= ADMIN =================
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

# ================= CREATE QUIZ =================
@app.route("/create_quiz",methods=["POST"])
def create_quiz():
    data=request.json

    quiz_id=str(uuid.uuid4())[:8]

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

# ================= QR =================
@app.route("/generate_qr/<quiz_id>")
def generate_qr(quiz_id):
    url = request.host_url + "quiz_info/" + quiz_id
    qr = qrcode.make(url)

    img_io = io.BytesIO()
    qr.save(img_io, 'PNG')
    img_io.seek(0)

    return send_file(img_io, mimetype='image/png')

@app.route("/quiz_info/<quiz_id>")
def quiz_info(quiz_id):

    # 🔐 NOT LOGGED IN → LOGIN
    if "user" not in session:
        return redirect("/login")

    # 👨‍🏫 ADMIN BLOCK
    email = session.get("user")
    if teacher_pattern.match(email):
        return redirect("/admin")

    # 👨‍🎓 STUDENT → SHOW QUIZ INFO PAGE
    q = quiz.find_one({"quiz_id": quiz_id}, {"_id":0})

    return render_template("quiz_info.html", quiz=q)
def attend_quiz(quiz_id):

    # 🔐 NOT LOGGED
    if "user" not in session:
        return redirect("/login")

    email = session.get("user")

    # 👨‍🏫 BLOCK ADMIN
    if teacher_pattern.match(email):
        return redirect("/admin")

    return render_template("student_quiz.html")

@app.route("/join/<quiz_id>")
def join_quiz(quiz_id):

    user = session.get("user")

    if not user:
        return redirect("/login")

    if teacher_pattern.match(user):
        return redirect("/admin")

    return redirect(f"/quiz/{quiz_id}")
    
# ================= FILE UPLOAD =================
@app.route("/upload_questions", methods=["POST"])
def upload_questions():

    file = request.files.get("file")

    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    filename = file.filename.lower()
    parsed = []

    # ================= CSV =================
    if filename.endswith(".csv"):
        df = pd.read_csv(file)

        for _, r in df.iterrows():
            parsed.append({
                "question": str(r["question"]),
                "options": [r["A"], r["B"], r["C"], r["D"]],
                "answer": str(r["answer"]).strip().upper()
            })

    # ================= TXT =================
    elif filename.endswith(".txt"):
        lines = file.read().decode("utf-8").split("\n")

        for line in lines:
            parts = line.strip().split("|")

            if len(parts) == 6:
                parsed.append({
                    "question": parts[0],
                    "options": parts[1:5],
                    "answer": parts[5].strip().upper()
                })

    # ================= DOCX =================
    elif filename.endswith(".docx"):
        doc = docx.Document(file)

        lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        parsed.extend(parse_block_questions(lines))

    # ================= PDF =================
    elif filename.endswith(".pdf"):
        with pdfplumber.open(file) as pdf:

            lines = []

            for p in pdf.pages:
                text = p.extract_text()
                if text:
                    lines.extend(text.split("\n"))

        parsed.extend(parse_block_questions(lines))

    else:
        return jsonify({"error": "Unsupported file"}), 400

    return jsonify(parsed)
# ================= PARSER =================
def parse_block_questions(lines):
    result = []
    current = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if "?" in line:
            if current and len(current["options"]) == 4 and current["answer"]:
                result.append(current)

            current = {"question": line, "options": [], "answer": ""}

        elif line.startswith(("A.", "B.", "C.", "D.")):
            if current:
                current["options"].append(line[2:].strip())

        elif "answer" in line.lower():
            if current:
                ans = line.split(":")[-1].strip().upper()
                if ans in ["A","B","C","D"]:
                    current["answer"] = ans

    if current and len(current["options"]) == 4 and current["answer"]:
        result.append(current)

    return result

# ================= GET QUIZZES =================
@app.route("/get_quizzes")
def get_quizzes():

    quizzes = list(quiz.find({}, {"_id":0}))

    student_id = session.get("user")

    now = datetime.now()

    for q in quizzes:

        start = datetime.fromisoformat(q["start_time"])
        end = datetime.fromisoformat(q["end_time"])

        attempt = submissions.find_one({
            "quiz_id": q["quiz_id"],
            "student_id": student_id
        })

        q["attempted"] = True if attempt else False

    return jsonify(quizzes)
# ================= CHECK ATTEMPT =================
@app.route("/check_attempt/<quiz_id>")
def check_attempt(quiz_id):

    student_id = session.get("user")

    existing = submissions.find_one({
        "quiz_id": quiz_id,
        "student_id": student_id
    })

    return jsonify({"attempted": True if existing else False})

# ================= LOAD QUIZ PAGE =================
@app.route("/quiz/<quiz_id>")
def attend_quiz(quiz_id):
    return render_template("student_quiz.html")

# ================= GET QUIZ =================
@app.route("/get_quiz/<quiz_id>")
def get_quiz(quiz_id):
    q = quiz.find_one({"quiz_id":quiz_id},{"_id":0})
    return jsonify(q)

# ================= GET QUESTIONS =================
@app.route("/get_questions/<quiz_id>")
def get_questions(quiz_id):

    q=list(questions.find({"quiz_id":quiz_id},{"_id":0}))
    return jsonify(q)

# ================= SUBMIT QUIZ =================
@app.route("/submit_quiz",methods=["POST"])
def submit_quiz():

    data=request.json
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

# ================= ACTIVITY =================
@app.route("/get_activity")
def get_activity():
    data=list(activity.find({},{"_id":0}))
    return jsonify(data)

# ================= SCORE =================
@app.route("/get_scores")
def get_scores():

    data=list(scores.find({},{"_id":0}))

    data=sorted(data,key=lambda x:x["correct"],reverse=True)

    for i,x in enumerate(data):
        if i==0: x["badge"]="🥇"
        elif i==1: x["badge"]="🥈"
        elif i==2: x["badge"]="🥉"
        else: x["badge"]="Bronze"

    return jsonify(data)


# ================= TELEGRAM =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
telegram_sessions = db["telegram_sessions"]

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

def main_menu_kb():
    return {
        "inline_keyboard": [
            [{"text": "➕ Create Quiz", "callback_data": "create"}],
            [{"text": "📊 Dashboard", "url": request.host_url}],
            [{"text": "❓ Help", "callback_data": "help"}]
        ]
    }

def edit_menu_kb():
    return {
        "inline_keyboard": [
            [{"text": "✏️ Edit Title", "callback_data": "edit_title"}],
            [{"text": "⏱ Edit Duration", "callback_data": "edit_duration"}],
            [{"text": "📅 Edit Start", "callback_data": "edit_start"}],
            [{"text": "📎 Re-upload Questions", "callback_data": "reupload"}],
            [{"text": "✅ Final Submit", "callback_data": "final_submit"}],
            [{"text": "❌ Cancel", "callback_data": "cancel"}],
        ]
    }

def require_prereq(user):
    data = (user or {}).get("data", {})
    missing = []
    if not data.get("title"): missing.append("Title")
    if not data.get("duration"): missing.append("Duration")
    if not data.get("start"): missing.append("Start time")
    return missing

def build_qr_bytes(url):
    qr = qrcode.make(url)
    bio = io.BytesIO()
    qr.save(bio, "PNG")
    bio.seek(0)
    return bio

def generate_styled_qr_card(quiz_id, title, duration):

    url = request.host_url + "join/" + quiz_id

    # ================= BASE QR =================
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=10,
        border=2
    )

    qr.add_data(url)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="#111827", back_color="white").convert("RGBA")

    # Resize QR
    qr_img = qr_img.resize((200, 200))

    # ================= ADD LOGO =================
    try:
        logo = Image.open("static/images/logo.png").convert("RGBA")

        # Resize logo
        logo_size = 50
        logo = logo.resize((logo_size, logo_size))

        # Position center
        pos = (
            qr_img.size[0]//2 - logo_size//2,
            qr_img.size[1]//2 - logo_size//2
        )

        # White circle behind logo
        circle = Image.new("RGBA", (logo_size+10, logo_size+10), (255,255,255,255))
        mask = Image.new("L", circle.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0,0,circle.size[0],circle.size[1]), fill=255)

        qr_img.paste(circle, (pos[0]-5, pos[1]-5), mask)
        qr_img.paste(logo, pos, logo)

    except:
        pass  # logo optional

    # ================= CREATE CARD =================
    card = Image.new("RGBA", (300, 380), (0,0,0,0))
    draw = ImageDraw.Draw(card)

    # Gradient simulation (top to bottom)
    for i in range(380):
        r = int(102 + (118-102)*(i/380))
        g = int(126 + (75-126)*(i/380))
        b = int(234 + (162-234)*(i/380))
        draw.line([(0,i),(300,i)], fill=(r,g,b))

    # Rounded corners mask
    mask = Image.new("L", (300,380), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle((0,0,300,380), radius=25, fill=255)
    card.putalpha(mask)

    # ================= PASTE QR =================
    card.paste(qr_img, (50, 100), qr_img)

    # ================= TEXT =================
    draw = ImageDraw.Draw(card)

    try:
        from PIL import ImageFont
        font_title = ImageFont.truetype("arial.ttf", 18)
        font_small = ImageFont.truetype("arial.ttf", 12)
    except:
        font_title = None
        font_small = None

    draw.text((90, 20), "Quiz ID: " + quiz_id, fill="white", font=font_small)
    draw.text((70, 45), title[:20], fill="white", font=font_title)
    draw.text((60, 70), f"Duration: {duration} mins", fill="white", font=font_small)
    draw.text((80, 320), "Scan to Join", fill="white", font=font_small)

    # ================= SAVE =================
    img_io = BytesIO()
    card.save(img_io, format="PNG")
    img_io.seek(0)

    return img_io

# ================= TELEGRAM WEBHOOK =================            
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    update = request.json or {}

    # ================= MESSAGE =================
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "").strip()
        doc = msg.get("document")

        user = telegram_sessions.find_one({"chat_id": chat_id}) or {}

        step = user.get("step")
        data = user.get("data", {})

        # ================= FILE HANDLING =================
        if doc:
            if step != "upload":
                missing = require_prereq(user)
                send_message(chat_id, f"⚠️ Complete first: {', '.join(missing)}")
                return "ok"

            file_id = doc["file_id"]
            fi = requests.get(f"{TELEGRAM_API}/getFile?file_id={file_id}").json()
            file_path = fi["result"]["file_path"]

            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            file_data = requests.get(file_url).content

            filename = os.path.join(UPLOAD_FOLDER, doc.get("file_name", "temp"))
            with open(filename, "wb") as f:
                f.write(file_data)

            parsed = []

            try:
                if filename.endswith(".pdf"):
                    with pdfplumber.open(filename) as pdf:
                        lines = []
                        for p in pdf.pages:
                            t = p.extract_text()
                            if t:
                                lines += t.split("\n")
                    parsed = parse_block_questions(lines)

                elif filename.endswith(".docx"):
                    d = docx.Document(filename)
                    lines = [p.text.strip() for p in d.paragraphs if p.text.strip()]
                    parsed = parse_block_questions(lines)

                elif filename.endswith(".txt"):
                    lines = file_data.decode(errors="ignore").split("\n")
                    parsed = parse_block_questions(lines)

                elif filename.endswith(".csv"):
                    df = pd.read_csv(filename)
                    df.columns = df.columns.str.lower()

                    for _, r in df.iterrows():
                        parsed.append({
                            "question": r["question"],
                            "options": [r["a"], r["b"], r["c"], r["d"]],
                            "answer": r["answer"].upper()
                        })

            finally:
                try: os.remove(filename)
                except: pass

            if not parsed:
                send_message(chat_id, "⚠️ No valid questions found")
                return "ok"

            telegram_sessions.update_one(
                {"chat_id": chat_id},
                {"$set": {"questions": parsed, "step": "review"}},
                upsert=True
            )

            send_message(chat_id, f"✅ {len(parsed)} questions uploaded", edit_menu_kb())
            return "ok"

        # ================= COMMANDS =================
        if text.lower() == "/start":
            telegram_sessions.delete_one({"chat_id": chat_id})
            send_message(chat_id, "👋 Welcome to PQDS", main_menu_kb())
            return "ok"

        if text.lower() == "/create_quiz":
            telegram_sessions.update_one(
                {"chat_id": chat_id},
                {"$set": {"step": "title", "data": {}}},
                upsert=True
            )
            send_message(chat_id, "📘 Enter Title")
            return "ok"

        if text.lower() == "/upload":
            missing = require_prereq(user)
            if missing:
                send_message(chat_id, f"⚠️ Fill first: {', '.join(missing)}")
                return "ok"

            telegram_sessions.update_one(
                {"chat_id": chat_id},
                {"$set": {"step": "upload"}}
            )
            send_message(chat_id, "📎 Upload file")
            return "ok"

        # ================= STEP FLOW =================
        if step == "title":
            telegram_sessions.update_one(
                {"chat_id": chat_id},
                {"$set": {"step": "duration", "data.title": text}}
            )
            send_message(chat_id, "⏱ Enter duration")
            return "ok"

        if step == "duration":
            try:
                dur = int(text)
                telegram_sessions.update_one(
                    {"chat_id": chat_id},
                    {"$set": {"step": "start", "data.duration": dur}}
                )
                send_message(chat_id, "📅 Enter start (YYYY-MM-DD HH:MM)")
            except:
                send_message(chat_id, "❌ Enter number")
            return "ok"

        if step == "start":
            try:
                dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
                telegram_sessions.update_one(
                    {"chat_id": chat_id},
                    {"$set": {"step": "upload", "data.start": dt.isoformat()}}
                )
                send_message(chat_id, "📎 Now upload file")
            except:
                send_message(chat_id, "❌ Wrong format")
            return "ok"

        send_message(chat_id, "Use /create_quiz")
        return "ok"

    # ================= CALLBACK =================
    if "callback_query" in update:
        cq = update["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        data_cb = cq["data"]
    
        # ✅ MUST
        tg("answerCallbackQuery", {
            "callback_query_id": cq["id"]
        })
    
        user = telegram_sessions.find_one({"chat_id": chat_id})
    
        # ===== CREATE =====
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    update = request.json or {}

    # ================= MESSAGE =================
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "").strip()

        user = telegram_sessions.find_one({"chat_id": chat_id}) or {}
        step = user.get("step")
        data = user.get("data", {})

        # START
        if text == "/start":
            telegram_sessions.update_one(
                {"chat_id": chat_id},
                {"$set": {"step": None, "data": {}}},
                upsert=True
            )

            send_message(chat_id, "👋 Welcome to PQDS Bot", main_menu_kb())
            return "ok"

        # TITLE INPUT
        if step == "title":
            telegram_sessions.update_one(
                {"chat_id": chat_id},
                {"$set": {"data.title": text, "step": None}}
            )
            send_message(chat_id, "✅ Title saved", edit_menu_kb())
            return "ok"

        # DURATION INPUT
        if step == "duration":
            telegram_sessions.update_one(
                {"chat_id": chat_id},
                {"$set": {"data.duration": int(text), "step": None}}
            )
            send_message(chat_id, "✅ Duration saved", edit_menu_kb())
            return "ok"

        # START TIME INPUT
        if step == "start":
            telegram_sessions.update_one(
                {"chat_id": chat_id},
                {"$set": {"data.start": text, "step": None}}
            )
            send_message(chat_id, "✅ Start time saved", edit_menu_kb())
            return "ok"

    # ================= CALLBACK BUTTONS =================
    if "callback_query" in update:
        cb = update["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        data_cb = cb["data"]

        user = telegram_sessions.find_one({"chat_id": chat_id}) or {}
        data = user.get("data", {})

        # CREATE
        if data_cb == "create":
            telegram_sessions.update_one(
                {"chat_id": chat_id},
                {"$set": {"step": None, "data": {}}},
                upsert=True
            )
            send_message(chat_id, "Enter Quiz Title:")
            telegram_sessions.update_one(
                {"chat_id": chat_id},
                {"$set": {"step": "title"}}
            )
            return "ok"

        # EDITS
        if data_cb == "edit_title":
            send_message(chat_id, "Enter new title:")
            telegram_sessions.update_one(
                {"chat_id": chat_id},
                {"$set": {"step": "title"}}
            )

        elif data_cb == "edit_duration":
            send_message(chat_id, "Enter duration (minutes):")
            telegram_sessions.update_one(
                {"chat_id": chat_id},
                {"$set": {"step": "duration"}}
            )

        elif data_cb == "edit_start":
            send_message(chat_id, "Enter start time (YYYY-MM-DD HH:MM):")
            telegram_sessions.update_one(
                {"chat_id": chat_id},
                {"$set": {"step": "start"}}
            )

        elif data_cb == "cancel":
            telegram_sessions.delete_one({"chat_id": chat_id})
            send_message(chat_id, "❌ Cancelled", main_menu_kb())

        elif data_cb == "final_submit":

            missing = require_prereq(user)
            if missing:
                send_message(chat_id, f"⚠️ Missing: {', '.join(missing)}")
                return "ok"

            quiz_id = str(uuid.uuid4())[:8]

            start_time = datetime.fromisoformat(data["start"])
            duration = int(data["duration"])
            end_time = start_time + timedelta(minutes=duration)

            quiz.insert_one({
                "quiz_id": quiz_id,
                "title": data["title"],
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration": duration
            })

            join_url = f"{request.host_url}join/{quiz_id}"
            img = generate_styled_qr_card(quiz_id, data["title"], duration)

            send_message(chat_id, f"✅ Quiz Created!\n{join_url}")
            send_photo(chat_id, img)

            telegram_sessions.delete_one({"chat_id": chat_id})

        return "ok"

    return "ok"
        
@app.route("/privacy")
def privacy():
    return """
    <html>
    <head>
        <title>PQDS Privacy Policy</title>
        <style>
            body {
                font-family: Arial;
                padding: 40px;
                line-height: 1.6;
                max-width: 800px;
                margin: auto;
            }
            h1 { color: #333; }
        </style>
    </head>
    <body>
        <h1>PQDS Privacy Policy</h1>

        <p>PQDS Quiz Bot collects only necessary data such as:</p>
        <ul>
            <li>Quiz details</li>
            <li>Questions uploaded</li>
            <li>Student scores</li>
            <li>Activity logs</li>
        </ul>

        <p>We do NOT sell or share your data with third parties.</p>

        <p>All data is used only for quiz management and analytics.</p>

        <p>By using this bot, you agree to this policy.</p>

        <p>Contact: pqds.support@gmail.com</p>
    </body>
    </html>
    """

# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)
