from flask import Flask, render_template, request, redirect, flash, jsonify, session
from pymongo import MongoClient
import re
import uuid
from datetime import datetime, timedelta
import pandas as pd
import docx
import pdfplumber
import os
import io
import qrcode
from io import BytesIO
from flask import send_file

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# ================= DATABASE =================
client = MongoClient("mongodb://Kevin2003:%40Kevin2003@ac-gjdvsbl-shard-00-00.gpbpget.mongodb.net:27017,ac-gjdvsbl-shard-00-01.gpbpget.mongodb.net:27017,ac-gjdvsbl-shard-00-02.gpbpget.mongodb.net:27017/?ssl=true&replicaSet=atlas-dc5j3m-shard-0&authSource=admin&appName=proctor")

db = client['proctor']

users_collection = db['users']
quiz = db["quizzes"]
questions = db["questions"]
activity = db["student_activity"]
scores = db["scores"]
submissions = db["submissions"]

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ================= EMAIL ROLE =================
teacher_pattern = re.compile(r'^[a-z0-9]+@bhc\.professor\.com$')
student_pattern = re.compile(r'^[a-z0-9]+@bhc\.student\.com$')

# ================= HOME =================
@app.route('/')
def spinner():
    return render_template('spinner.html')

# ================= LOGIN =================
@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        user = users_collection.find_one({"email":email,"password":password})

        if user:

            session["user"] = email  
            session["name"] = user["name"]  # ✅ FIX SESSION

            if teacher_pattern.match(email):
                return redirect("/admin")
            elif student_pattern.match(email):
                return redirect("/student")

        flash("Invalid credentials")
        return redirect("/login")

    return render_template("login.html")

# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ================= SIGNUP =================
@app.route("/signup",methods=["GET","POST"])
def signup():

    if request.method == "POST":

        data={
            "name":request.form["name"],
            "email":request.form["email"],
            "password":request.form["password"],
            "role":request.form["role"]
        }

        users_collection.insert_one(data)

        flash("Account Created Successfully")
        return redirect("/login")

    return render_template("signup.html")

# ================= ADMIN =================
@app.route("/admin")
def admin_dashboard():

    if "user" not in session:
        return redirect("/login")

    return render_template("admin_dashboard.html")

# ================= STUDENT =================
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

    quiz_doc={
        "quiz_id":quiz_id,
        "title":data["title"],
        "start_time":start_time.isoformat(),
        "end_time":end_time.isoformat(),
        "duration":duration,
        "created_at":datetime.now()
    }

    quiz.insert_one(quiz_doc)

    # save questions
    for q in data.get("questions",[]):

        questions.insert_one({
            "quiz_id":quiz_id,
            "question":q["question"],
            "options":q["options"],
            "answer":q["answer"]
        })

    return jsonify({"msg": f'{data["title"]} Created Successfully',"quiz_id": quiz_id})
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

# ================= FILE UPLOAD =================
@app.route("/upload_questions", methods=["POST"])
def upload_questions():

    file = request.files["file"]
    filename = file.filename

    parsed_questions = []

    # CSV
    if filename.endswith(".csv"):
        df = pd.read_csv(file)

        for _, row in df.iterrows():
            parsed_questions.append({
                "question": row["question"],
                "options": [row["A"], row["B"], row["C"], row["D"]],
                "answer": row["answer"]
            })

    # TXT
    elif filename.endswith(".txt"):
        for line in file:
            parts = line.decode().strip().split("|")

            if len(parts) == 6:
                parsed_questions.append({
                    "question": parts[0],
                    "options": parts[1:5],
                    "answer": parts[5]
                })

    return jsonify(parsed_questions)

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

    # prevent multiple attempts
    existing = submissions.find_one({
        "quiz_id": data["quiz_id"],
        "student_id": student_id
    })

    if existing:
        return jsonify({"msg":"Already submitted"})

    student_id = session.get("user")
    name = session.get("name")

    submissions.insert_one({
        "quiz_id": data["quiz_id"],
        "student_id": student_id,
        "name": name,   # ✅ FIX
        "correct":data["correct"],
        "wrong":data["wrong"],
        "skipped":data["skipped"]
    })


    scores.insert_one({
        "quiz_id": data["quiz_id"],
        "student_id": student_id,
        "name": name,   # ✅ FIX
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



# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)