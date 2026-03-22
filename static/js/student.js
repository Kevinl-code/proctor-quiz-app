formatDateTime(q.start_time)
formatDateTime(q.end_time)

async function loadQuizzes(){

let res=await fetch("/get_quizzes")

let quizzes=await res.json()
function getStatusColor(status){

if(status==="upcoming") return "#3b82f6"
if(status==="ongoing") return "#22c55e"
if(status==="completed") return "#a855f7"
if(status==="expired") return "#ef4444"

}
quizzes.forEach(q=>{

html += `
<div class="quiz-card">

<h3>${q.title}</h3>

<p style="color:${getStatusColor(q.status)}">
${q.status.toUpperCase()}
</p>

<button 
${q.status!=="ongoing" ? "disabled" : ""}
onclick="startQuiz('${q.quiz_id}')">

Start Quiz

</button>

</div>
`

})

}

loadQuizzes()

