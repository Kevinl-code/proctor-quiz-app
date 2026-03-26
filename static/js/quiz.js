let questions = []
let current = 0
let answers = {}

let timerInterval = null

window.onload = loadQuiz

// ================= LOAD QUIZ =================
async function loadQuiz(){
    function enterFullscreen(){

let elem = document.documentElement

if(elem.requestFullscreen){
  elem.requestFullscreen()
}

}

let quizId = window.location.pathname.split("/").pop()

// ✅ GET QUIZ DETAILS (FIX)
let resQuiz = await fetch("/get_quiz/"+quizId)
let quiz = await resQuiz.json()

// set title
document.getElementById("quizTitle").innerText = quiz.title

// TIME VALIDATION
let now = new Date()
let start = new Date(quiz.start_time)
let end = new Date(quiz.end_time)

if(now < start){
alert("Quiz not started yet")
window.location.href="/student"
return
}

if(now > end){
alert("Quiz expired")
window.location.href="/student"
return
}

// check attempt
let resCheck = await fetch("/check_attempt/"+quizId)
let attempt = await resCheck.json()

if(attempt.attempted){
alert("You already attended this quiz")
window.location.href="/student"
return
}

// ✅ GET QUESTIONS (CORRECT)
let resQ = await fetch("/get_questions/"+quizId)
questions = await resQ.json()

if(questions.length === 0){
alert("No questions available")
window.location.href="/student"
return
}

renderQuestion()

startTimerRealtime(quiz.end_time)
enterFullscreen()
}


// ================= RENDER =================
function renderQuestion(){

let q = questions[current]

document.getElementById("questionText").innerText =
(current+1)+". "+q.question

let optionsHTML = '<div class="options-grid">';

q.options.forEach((opt)=>{

let checked = answers[current] === opt ? "checked" : ""

optionsHTML += `
<label class="option-card">

<input type="radio" name="option"
value="${opt}"
${checked}
onchange="selectAnswer('${opt}')">

<span>${opt}</span>

</label>
`

})

optionsHTML += '</div>';

document.getElementById("optionsBox").innerHTML = optionsHTML

// buttons
document.getElementById("prevBtn").style.display =
current === 0 ? "none" : "inline-block"

document.getElementById("nextBtn").style.display =
current === questions.length-1 ? "none" : "inline-block"

document.getElementById("submitBtn").style.display =
current === questions.length-1 ? "inline-block" : "none"

}


// ================= SELECT =================
function selectAnswer(val){
answers[current] = val
}


// ================= NAV =================
function nextQuestion(){
if(current < questions.length-1){
current++
renderQuestion()
}
}

function prevQuestion(){
if(current > 0){
current--
renderQuestion()
}
}


// ================= TIMER =================
function startTimerRealtime(endTime){

let timerInterval = setInterval(()=>{

let now = new Date()
let end = new Date(endTime)

let diff = Math.floor((end - now)/1000)

if(diff <= 0){
clearInterval(timerInterval)
autoSubmit()
return
}

let min = Math.floor(diff/60)
let sec = diff % 60

document.getElementById("timer").innerText =
`${String(min).padStart(2,'0')}:${String(sec).padStart(2,'0')}`

},1000)

}

// ================= CONFIRM =================
function confirmSubmit(){

let ok = confirm("Final Submit? You cannot change answers.")

if(ok){
submitQuiz()
}

}


// ================= AUTO =================
function autoSubmit(){

alert("Time Over! Auto Submitting...")
submitQuiz()

}


// ================= SUBMIT =================
async function submitQuiz(){

clearInterval(timerInterval)

let quizId = window.location.pathname.split("/").pop()

let correct = 0
let wrong = 0
let skipped = 0

questions.forEach((q,i)=>{

let userAnswer = answers[i]

if(!userAnswer){
skipped++
}
else{

let correctOption = q.options[
["A","B","C","D"].indexOf(q.answer.toUpperCase())
]

if(userAnswer === correctOption){
correct++
}else{
wrong++
}

}

})

await fetch("/submit_quiz",{

method:"POST",
headers:{"Content-Type":"application/json"},

body:JSON.stringify({
  quiz_id: quizId,
  correct,
  wrong,
  skipped,
  violations: violations  

})

})

alert("Submitted Successfully")
window.location.href="/student"

}
let violations = []

function logViolation(type){

violations.push({
  type: type,
  time: new Date().toLocaleTimeString()
})

console.log("Violation:", type)

}
document.addEventListener("visibilitychange", () => {
  if(document.hidden){
    logViolation("Tab Switched / Minimized")
  }
})
document.addEventListener("visibilitychange", () => {
  if(document.hidden){
    logViolation("Tab Switched / Minimized")
  }
})
window.addEventListener("blur", () => {
  logViolation("Window Lost Focus")
})
window.addEventListener("blur", () => {
  logViolation("Window Lost Focus")
})
document.addEventListener("copy", ()=> logViolation("Copy Attempt"))
document.addEventListener("paste", ()=> logViolation("Paste Attempt"))
document.addEventListener("cut", ()=> logViolation("Cut Attempt"))
