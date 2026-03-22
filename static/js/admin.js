// ================= INIT =================

window.addEventListener("load", () => {
    let qr = document.getElementById("qrSection")
    if(qr) qr.style.display = "none"
})


// ================= FORMAT DATE =================

function formatDateTime(dateStr){

let d = new Date(dateStr)

let days = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]

let dayName = days[d.getDay()]

let day = String(d.getDate()).padStart(2,'0')
let month = String(d.getMonth()+1).padStart(2,'0')
let year = d.getFullYear()

let hours = d.getHours()
let minutes = String(d.getMinutes()).padStart(2,'0')

let ampm = hours >= 12 ? "PM" : "AM"

hours = hours % 12 || 12

return `${dayName}, ${day}-${month}-${year} ${hours}:${minutes} ${ampm}`
}


// ================= PANEL =================

function showPanel(panel){

["quizPanel","activityPanel","scorePanel"].forEach(id=>{
    document.getElementById(id).style.display="none"
})

document.getElementById(panel).style.display="block"

}


// ================= STORAGE =================

let questions=[]


// ================= MANUAL MODE =================

function manualMode(){

document.getElementById("uploadArea").style.display="none"

document.getElementById("manualQuestions").innerHTML=`

<div style="margin-top:15px">

<input id="q" placeholder="Question" class="input">

<input id="a" placeholder="Option A" class="input">
<input id="b" placeholder="Option B" class="input">
<input id="c" placeholder="Option C" class="input">
<input id="d" placeholder="Option D" class="input">

<input id="ans" placeholder="Correct Answer (A/B/C/D)" class="input">

<button class="btn-secondary" onclick="addQuestion()">Add Question</button>

</div>
`
}


// ================= UPLOAD MODE =================

function uploadMode(){

document.getElementById("manualQuestions").innerHTML=""
document.getElementById("uploadArea").style.display="block"

let input = document.getElementById("fileUpload")

if(input){
input.onchange = function(){
    let file = this.files[0]
    document.getElementById("fileName").innerText =
        file ? "Selected: "+file.name : "No file selected"
}
}

}


// ================= ADD QUESTION =================

function addQuestion(){

let q=document.getElementById("q").value.trim()
let a=document.getElementById("a").value.trim()
let b=document.getElementById("b").value.trim()
let c=document.getElementById("c").value.trim()
let d=document.getElementById("d").value.trim()
let ans=document.getElementById("ans").value.trim().toUpperCase()

if(!q || !a || !b || !c || !d || !ans){
alert("Fill all fields")
return
}

questions.push({
question:q,
options:[a,b,c,d],
answer:ans
})

alert("Question Added")

document.querySelectorAll("#manualQuestions input").forEach(i=>i.value="")

}


// ================= CREATE QUIZ =================

async function createQuiz(){

let title=document.getElementById("quizTitle").value.trim()
let start=document.getElementById("quizStart").value
let duration=parseInt(document.getElementById("quizDuration").value)

if(!title || !start || !duration){
alert("Fill all quiz details")
return
}

if(questions.length===0){
alert("Add or upload questions first")
return
}

// calculate end time
let startDate=new Date(start)
let endDate=new Date(startDate.getTime() + duration*60000)

let res=await fetch("/create_quiz",{
method:"POST",
headers:{"Content-Type":"application/json"},
body:JSON.stringify({
title,
start,
end:endDate.toISOString(),
duration,
questions
})
})

let data=await res.json()

alert(data.msg)

// ✅ GENERATE QR
generateQR(data.quiz_id, title, duration)

// reset
questions=[]
document.getElementById("manualQuestions").innerHTML=""
document.getElementById("uploadArea").style.display="none"

}


// ================= QR GENERATION =================
function generateQR(quizId, title, duration){

let url = window.location.origin + "/join/" + quizId

let qrBox = document.getElementById("qrCanvas")
qrBox.innerHTML = ""

// ✅ CREATE QR
new QRCode(qrBox, {

    text: url,
    width: 200,
    height: 200,
    drawer: "svg",  

    // 🔥 IMPORTANT (fix logo + design)
    correctLevel: QRCode.CorrectLevel.H,  // REQUIRED for logo
    quietZone: 10,

    // 🎯 DOT STYLE (modern)
    dotScale: 0.9,

    // 🎨 COLORS
    colorDark: "#111827",
    colorLight: "#ffffff",

    // 🧱 CORNER STYLE
    PO: "#111827",
    PI: "#111827",

    // 🖼 LOGO CENTER FIX
    logo: "/static/images/logo.png",
    logoWidth: 70,
    logoHeight: 70,
    logoBackgroundColor: "#ffffff",
    logoBackgroundTransparent: false

})

// SET DETAILS
document.getElementById("qrId").innerText = quizId
document.getElementById("qrTitle").innerText = title
document.getElementById("qrDetails").innerText = "Duration: " + duration + " mins"

// SHOW
document.getElementById("qrSection").style.display = "block"
}
// ================= RESET =================

function resetQuiz(){

questions=[]

document.getElementById("quizTitle").value=""
document.getElementById("quizStart").value=""
document.getElementById("quizDuration").value=""

document.getElementById("manualQuestions").innerHTML=""
document.getElementById("uploadArea").style.display="none"

document.getElementById("qrSection").style.display="none"

alert("Ready for new quiz")

}


// ================= DOWNLOAD QR =================

function downloadQR(){

let card = document.getElementById("qrCard")

html2canvas(card).then(canvas => {

    let link = document.createElement("a")
    link.download = "quiz_qr.png"
    link.href = canvas.toDataURL()
    link.click()

})

}

// ================= UPLOAD =================

async function uploadQuestions(){

let file=document.getElementById("fileUpload").files[0]

if(!file){
alert("Select file")
return
}

let formData=new FormData()
formData.append("file",file)

let res=await fetch("/upload_questions",{
method:"POST",
body:formData
})

let data=await res.json()

if(!Array.isArray(data)){
alert("Invalid format")
return
}

questions=data

alert(data.length+" Questions Uploaded")

}


// ================= ACTIVITY =================

async function loadActivity(){

showPanel("activityPanel")

let res=await fetch("/get_activity")
let data=await res.json()

let table=document.querySelector("#activityTable tbody")
table.innerHTML=""

if(data.length===0){
table.innerHTML=`<tr><td colspan="7">No Activity</td></tr>`
return
}

data.forEach(x=>{
table.innerHTML+=`
<tr>
<td>${x.name||"-"}</td>
<td>${x.student_id||"-"}</td>
<td>${x.question_answered||"-"}</td>
<td>${x.correct||"-"}</td>
<td>${x.wrong||"-"}</td>
<td>${x.skipped||"-"}</td>
<td>${x.violation_type||"-"}</td>
</tr>`
})

}


// ================= SCORE =================

async function loadScore(){

showPanel("scorePanel")

let res=await fetch("/get_scores")
let data=await res.json()

let table=document.querySelector("#scoreTable tbody")
table.innerHTML=""

if(data.length===0){
table.innerHTML=`<tr><td colspan="7">No Scores</td></tr>`
return
}

data.sort((a,b)=>b.correct-a.correct)

data.forEach((x,i)=>{

let badge="Bronze"
if(i===0) badge="🥇"
else if(i===1) badge="🥈"
else if(i===2) badge="🥉"

table.innerHTML+=`
<tr>
<td>${i+1}</td>
<td>${x.name||"-"}</td>
<td>${x.student_id||"-"}</td>
<td>${x.correct}</td>
<td>${x.wrong}</td>
<td>${x.result}</td>
<td>${badge}</td>
</tr>`
})

}
