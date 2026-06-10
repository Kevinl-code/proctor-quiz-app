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

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client['proctor']
BOT_TOKEN = os.getenv("BOT_TOKEN")
SECRET_KEY = os.getenv("SECRET_KEY", "fallback_secret")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

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

# ================= FILE PARSER MECHANISM =================
def extract_questions_from_file(file, filename):
    parsed = []
    if filename.endswith(".csv"):
        df = pd.read_csv(file)
        for _, r in df.iterrows():
            parsed.append({
                "question": str(r["question"]),
                "options": [r["A"], r["B"], r["C"], r["D"]],
                "answer": str(r["answer"]).strip().upper()
            })
    elif filename.endswith(".txt"):
        lines = file.read().decode("utf-8").splitlines()
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
    return parsed

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

# ================= QR & ATTEMPTS =================
@app.route("/generate_qr/<quiz_id>")
def generate_qr(quiz_id):
    url = request.host_url + "join/" + quiz_id
    qr = qrcode.make(url)

    img_io = io.BytesIO()
    qr.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')

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

# ================= TELEGRAM KEYBOARDS & BUILDERS =================
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

def generate_styled_qr_card(quiz_id, title, duration):
    url = request.host_url + "join/" + quiz_id
    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_H, box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="#111827", back_color="white").convert("RGBA").resize((200, 200))

    try:
        logo = Image.open("static/images/logo.png").convert("RGBA")
        logo_size = 50
        logo = logo.resize((logo_size, logo_size))
        pos = (qr_img.size[0]//2 - logo_size//2, qr_img.size[1]//2 - logo_size//2)

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

    img_io = BytesIO()
    card.save(img_io, format="PNG")
    img_io.seek(0)
    return img_io

# ================= TELEGRAM WEBHOOK =================            
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    update = request.json or {}

    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        
        user = telegram_sessions.find_one({"chat_id": chat_id}) or {}
        step = user.get("step")
        data = user.get("data", {})

        if "text" in msg:
            text = msg["text"].strip()

            if text.lower() == "/start":
                telegram_sessions.delete_one({"chat_id": chat_id})
                send_message(chat_id, "🤖 Welcome to Quiz Bot", main_menu_kb())
                return "ok"

            if step == "title":
                telegram_sessions.update_one({"chat_id": chat_id}, {"$set": {"data.title": text, "step": None}}, upsert=True)
                send_message(chat_id, "✅ Title saved", edit_menu_kb())
                return "ok"

            if step == "duration":
                try:
                    duration = int(text)
                    telegram_sessions.update_one({"chat_id": chat_id}, {"$set": {"data.duration": duration, "step": None}}, upsert=True)
                    send_message(chat_id, "✅ Duration saved", edit_menu_kb())
                except:
                    send_message(chat_id, "⚠️ Enter valid number (minutes)")
                return "ok"

            if step == "start":
                try:
                    dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
                    telegram_sessions.update_one({"chat_id": chat_id}, {"$set": {"data.start": dt.isoformat(), "step": None}}, upsert=True)
                    send_message(chat_id, "✅ Start time saved", edit_menu_kb())
                except:
                    send_message(chat_id, "⚠️ Format: YYYY-MM-DD HH:MM")
                return "ok"

        # Processing dynamic document streams (nested properly inside message update structure)
        if "document" in msg:
            file_id = msg["document"]["file_id"]
            res = requests.get(f"{TELEGRAM_API}/getFile", params={"file_id": file_id}).json()
            path = res["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{path}"
            file_data = requests.get(file_url).content
            
            memory_file = BytesIO(file_data)
            parsed_questions = extract_questions_from_file(memory_file, msg["document"]["file_name"].lower())
            
            telegram_sessions.update_one(
                {"chat_id": chat_id},
                {"$set": {"data.questions": parsed_questions, "step": None}}
            )
            send_message(chat_id, f"✅ Processed {len(parsed_questions)} questions from file structure!", edit_menu_kb())
            return "ok"

    if "callback_query" in update:
        cb = update["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        data_cb = cb["data"]

        requests.post(f"{TELEGRAM_API}/answerCallbackQuery", json={"callback_query_id": cb["id"]})

        user = telegram_sessions.find_one({"chat_id": chat_id}) or {}
        data = user.get("data", {})

        if data_cb == "create":
            telegram_sessions.update_one({"chat_id": chat_id}, {"$set": {"step": "title", "data": {}}}, upsert=True)
            send_message(chat_id, "Enter Quiz Title:")
            return "ok"

        if data_cb == "edit_title":
            send_message(chat_id, "Enter new title:")
            telegram_sessions.update_one({"chat_id": chat_id}, {"$set": {"step": "title"}}, upsert=True)
            return "ok"

        if data_cb == "edit_duration":
            send_message(chat_id, "Enter duration (minutes):")
            telegram_sessions.update_one({"chat_id": chat_id}, {"$set": {"step": "duration"}}, upsert=True)
            return "ok"

        if data_cb == "edit_start":
            send_message(chat_id, "Enter start time (YYYY-MM-DD HH:MM):")
            telegram_sessions.update_one({"chat_id": chat_id}, {"$set": {"step": "start"}}, upsert=True)
            return "ok"

        if data_cb == "reupload":
            send_message(chat_id, "Send/Upload your question file (.csv, .txt, .docx, .pdf):")
            telegram_sessions.update_one({"chat_id": chat_id}, {"$set": {"step": "upload"}}, upsert=True)
            return "ok"

        if data_cb == "cancel":
            telegram_sessions.delete_one({"chat_id": chat_id})
            send_message(chat_id, "❌ Cancelled", main_menu_kb())
            return "ok"

        if data_cb == "final_submit":
            missing = require_prereq(user)
            if missing:
                send_message(chat_id, f"⚠️ Missing fields: {', '.join(missing)}")
                return "ok"

            try:
                quiz_id = str(uuid.uuid4())[:8]
                start_time = datetime.fromisoformat(data["start"])
                duration = int(data["duration"])
                end_time = start_time + timedelta(minutes=duration)

                quiz.insert_one({
                    "quiz_id": quiz_id,
                    "title": data["title"],
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "duration": duration,
                    "created_at": datetime.now()
                })

                for q in data.get("questions", []):
                    questions.insert_one({
                        "quiz_id": quiz_id,
                        "question": q["question"],
                        "options": q["options"],
                        "answer": q["answer"]
                    })

                join_url = f"{request.host_url}join/{quiz_id}"
                img = generate_styled_qr_card(quiz_id, data["title"], duration)

                send_message(chat_id, f"✅ Quiz Created Successfully!\nLink: {join_url}")
                send_photo(chat_id, img)
                telegram_sessions.delete_one({"chat_id": chat_id})

            except Exception as e:
                send_message(chat_id, f"❌ Storage Error: {str(e)}")

        return "ok"

    return "ok"
        
@app.route("/privacy")
def privacy():
    return """
    <html>
    <head><title>PQDS Privacy Policy</title></head>
    <body style="font-family: Arial; padding: 40px; line-height: 1.6; max-width: 800px; margin: auto;">
        <h1>PQDS Privacy Policy</h1>
        <p>PQDS Quiz Bot collects only necessary data such as quiz details, questions uploaded, student scores, and activity logs.</p>
        <p>We do NOT sell or share your data with third parties.</p>
        <p>Contact: pqds.support@gmail.com</p>
    </body>
    </html>
    """

if __name__ == "__main__":
    app.run(debug=True)
