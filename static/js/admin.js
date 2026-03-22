window.addEventListener("load", () => {

let qr = document.getElementById("qrSection")

if(qr){
qr.style.display = "none"
}

})

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

hours = hours % 12
hours = hours ? hours : 12

return `${dayName}, ${day}-${month}-${year} ${hours}:${minutes} ${ampm}`

}

// ================= PANEL CONTROL =================

function showPanel(panel){

document.getElementById("quizPanel").style.display="none"
document.getElementById("activityPanel").style.display="none"
document.getElementById("scorePanel").style.display="none"

document.getElementById(panel).style.display="block"

}


// ================= OPEN QUIZ PANEL =================

function openQuiz(){
showPanel("quizPanel")
}


// ================= QUESTION STORAGE =================

let questions=[]


// ================= MANUAL QUESTION MODE =================

function manualMode(){

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

`;

}


// ================= UPLOAD MODE =================

function uploadMode(){

document.getElementById("manualQuestions").innerHTML=`

<div style="margin-top:15px">

<input type="file" id="fileUpload" accept=".csv,.txt,.docx,.pdf">

<div id="fileName" style="margin-top:5px;font-size:13px;color:#666">
No file selected
</div>

<button class="btn-secondary" onclick="uploadQuestions()">Upload</button>

</div>

`;


// show selected filename
setTimeout(()=>{

let input=document.getElementById("fileUpload")

if(input){

input.addEventListener("change",function(){

let file=this.files[0]

if(file){
document.getElementById("fileName").innerText="Selected: "+file.name
}

})

}

},100)

}


// ================= ADD QUESTION =================

function addQuestion(){

let q=document.getElementById("q").value.trim()
let a=document.getElementById("a").value.trim()
let b=document.getElementById("b").value.trim()
let c=document.getElementById("c").value.trim()
let d=document.getElementById("d").value.trim()
let ans=document.getElementById("ans").value.trim()

if(!q || !a || !b || !c || !d || !ans){

alert("Please fill all fields")
return

}

questions.push({

question:q,
options:[a,b,c,d],
answer:ans.toUpperCase()

})

alert("Question Added Successfully")

// clear inputs
document.getElementById("q").value=""
document.getElementById("a").value=""
document.getElementById("b").value=""
document.getElementById("c").value=""
document.getElementById("d").value=""
document.getElementById("ans").value=""

}


// ================= CREATE QUIZ =================

async function createQuiz(){

let title=document.getElementById("quizTitle").value.trim()
let start=document.getElementById("quizStart").value
let duration=document.getElementById("quizDuration").value

if(!title || !start || !duration){

alert("Please fill quiz title, start time and duration")
return

}

if(questions.length===0){

alert("Please add or upload questions first")
return

}

// calculate END TIME
let startDate = new Date(start)
let endDate = new Date(startDate.getTime() + duration*60000)

let res=await fetch("/create_quiz",{

method:"POST",

headers:{
"Content-Type":"application/json"
},

body:JSON.stringify({

title:title,
start:start,
end:endDate.toISOString(),
duration:duration,
questions:questions

})

})


let data = await res.json()

alert(data.msg)

// ✅ SHOW QR HERE
let qr = document.getElementById("qrImage")

qr.src = "/generate_qr/" + data.quiz_id
qr.style.display = "block"

// reset
// ✅ SHOW QR
generateQR(data.quiz_id, title, duration)
questions=[]
document.getElementById("manualQuestions").innerHTML=""
document.getElementById("uploadArea").style.display="block"
}
function resetQuiz(){

questions = []

document.getElementById("quizTitle").value = ""
document.getElementById("quizStart").value = ""
document.getElementById("quizDuration").value = ""

document.getElementById("manualQuestions").innerHTML = ""

document.getElementById("qrSection").style.display = "none"

alert("Ready for new quiz")
}

function generateQR(quizId, title, duration){

let url = window.location.origin + "/join/" + quizId

// clear old QR
document.getElementById("qrCanvas").innerHTML = ""

// create QR
let qr = new QRCode(document.getElementById("qrCanvas"), {
    text: url,
    width: 180,
    height: 180,
    colorDark: "#000000",
    colorLight: "#ffffff",
    correctLevel: QRCode.CorrectLevel.H
})

// set details
document.getElementById("qrTitle").innerText = title
document.getElementById("qrDetails").innerText = "Duration: " + duration + " mins"

// show section
document.getElementById("qrSection").style.display = "block"

}
function downloadQR(){

let card = document.getElementById("qrCard")

html2canvas(card).then(canvas => {

    let link = document.createElement("a")
    link.download = "quiz_qr.png"
    link.href = canvas.toDataURL()
    link.click()

})

}
function shareQR(){

let img = document.getElementById("qrImage").src

if(navigator.share){
    navigator.share({
        title: "Join Quiz",
        url: img
    })
}else{
    alert("Sharing not supported, please download QR")
}

}
// ================= FILE QUESTION UPLOAD =================

async function uploadQuestions(){

let fileInput = document.getElementById("fileUpload")

if(!fileInput){
alert("Upload field not found")
return
}

let file = fileInput.files[0]

if(!file){
alert("Please select a file")
return
}

let formData = new FormData()
formData.append("file", file)

try{

let res = await fetch("/upload_questions",{
method:"POST",
body:formData
})

let data = await res.json()

if(!Array.isArray(data)){
alert("Invalid file format")
return
}

questions = data

alert(data.length + " Questions Uploaded Successfully")

}catch(err){

alert("Upload failed")
console.log(err)

}

}

document.getElementById("qrImage").src ="/generate_qr/" + data.quiz_id

// ================= LOAD STUDENT ACTIVITY =================

async function loadActivity(){

showPanel("activityPanel")

let res=await fetch("/get_activity")

let data=await res.json()

let table=document.querySelector("#activityTable tbody")

table.innerHTML=""

if(data.length===0){

table.innerHTML=`<tr><td colspan="7">No Activity Found</td></tr>`
return

}

data.forEach(x=>{

table.innerHTML+=`

<tr>

<td>${x.name || "-"}</td>
<td>${x.student_id || "-"}</td>
<td>${x.question_answered || "-"}</td>
<td>${x.correct || "-"}</td>
<td>${x.wrong || "-"}</td>
<td>${x.skipped || "-"}</td>
<td>${x.violation_type || "-"}</td>

</tr>

`

})

}


// ================= LOAD SCOREBOARD =================

async function loadScore(){

showPanel("scorePanel")

let res=await fetch("/get_scores")

let data=await res.json()

let table=document.querySelector("#scoreTable tbody")

table.innerHTML=""

if(data.length===0){

table.innerHTML=`<tr><td colspan="7">No Scores Available</td></tr>`
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
<td>${x.name}</td>
<td>${x.student_id}</td>
<td>${x.correct}</td>
<td>${x.wrong}</td>
<td>${x.result}</td>
<td>${badge}</td>

</tr>

`

})

}
