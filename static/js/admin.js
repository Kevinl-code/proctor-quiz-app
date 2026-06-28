// ======================================================
// PQDS ADMIN DASHBOARD
// ======================================================

let questions = [];
let qrInstance = null;

// ======================================================
// PANEL SWITCH
// ======================================================

function showPanel(id){

    document.querySelectorAll(".panel").forEach(p=>{
        p.style.display="none";
    });

    document.getElementById(id).style.display="block";
}

// ======================================================
// MANUAL MODE
// ======================================================

function manualMode(){

    document.getElementById("uploadArea").style.display="none";
    document.getElementById("manualQuestions").style.display="block";

    if(document.getElementById("manualQuestions").innerHTML===""){
        addQuestion();
    }
}

// ======================================================
// FILE MODE
// ======================================================

function uploadMode(){

    document.getElementById("manualQuestions").style.display="none";
    document.getElementById("uploadArea").style.display="block";
}

// ======================================================
// ADD QUESTION
// ======================================================

function addQuestion(){

    const container=document.getElementById("manualQuestions");

    const index=container.children.length;

    container.insertAdjacentHTML("beforeend",`

<div class="question-card">

<h4>Question ${index+1}</h4>

<input class="question" placeholder="Question">

<input class="option" placeholder="Option A">

<input class="option" placeholder="Option B">

<input class="option" placeholder="Option C">

<input class="option" placeholder="Option D">

<select class="answer">

<option>A</option>
<option>B</option>
<option>C</option>
<option>D</option>

</select>

<hr>

</div>

`);

}

// ======================================================
// COLLECT QUESTIONS
// ======================================================

function collectQuestions(){

    questions=[];

    const cards=document.querySelectorAll(".question-card");

    cards.forEach(card=>{

        const q=card.querySelector(".question").value;

        const opts=[...card.querySelectorAll(".option")].map(x=>x.value);

        const ans=card.querySelector(".answer").value;

        questions.push({

            question:q,
            options:opts,
            answer:ans

        });

    });

}

// ======================================================
// FILE NAME
// ======================================================

const uploader=document.getElementById("fileUpload");

if(uploader){

uploader.addEventListener("change",()=>{

const file=uploader.files[0];

document.getElementById("fileName").innerHTML=file?
file.name:
"No file selected";

});

}

// ======================================================
// UPLOAD QUESTIONS
// ======================================================

async function uploadQuestions(){

    const file=document.getElementById("fileUpload").files[0];

    if(!file){

        alert("Choose file");

        return;

    }

    let fd=new FormData();

    fd.append("file",file);

    const res=await fetch("/upload_questions",{

        method:"POST",
        body:fd

    });

    questions=await res.json();

    alert(`${questions.length} Questions Imported`);

}

// ======================================================
// CREATE QUIZ
// ======================================================

async function createQuiz(){

    if(document.getElementById("manualQuestions").style.display!="none"){

        collectQuestions();

    }

    if(questions.length===0){

        alert("No questions found");

        return;

    }

    const payload={

        title:document.getElementById("quizTitle").value,

        start:document.getElementById("quizStart").value,

        duration:document.getElementById("quizDuration").value,

        questions:questions

    };

    const res=await fetch("/create_quiz",{

        method:"POST",

        headers:{

            "Content-Type":"application/json"

        },

        body:JSON.stringify(payload)

    });

    const data=await res.json();

    if(!data.quiz_id){

        alert("Creation Failed");

        return;

    }

    generateQR(data.quiz_id,payload);

}

// ======================================================
// QR
// ======================================================

function generateQR(id,payload){

document.getElementById("qrSection").style.display="block";

document.getElementById("qrId").innerHTML=id;

document.getElementById("qrTitle").innerHTML=payload.title;

document.getElementById("qrDetails").innerHTML=

`Duration : ${payload.duration} mins`;

document.getElementById("qrCanvas").innerHTML="";

qrInstance=new QRCodeStyling({

width:220,

height:220,

type:"canvas",

data:window.location.origin+"/join/"+id,

image:"/static/images/logo.png",

dotsOptions:{
color:"#111827",
type:"rounded"
},

cornersSquareOptions:{
type:"extra-rounded"
},

backgroundOptions:{
color:"#ffffff"
},

imageOptions:{
crossOrigin:"anonymous",
margin:4
}

});

qrInstance.append(document.getElementById("qrCanvas"));

}

// ======================================================
// DOWNLOAD QR
// ======================================================

function downloadQR(){

if(qrInstance){

qrInstance.download({

name:"QuizQR",

extension:"png"

});

}

}

// ======================================================
// RESET
// ======================================================

function resetQuiz(){

questions=[];

document.getElementById("quizTitle").value="";

document.getElementById("quizStart").value="";

document.getElementById("quizDuration").value="";

document.getElementById("manualQuestions").innerHTML="";

document.getElementById("qrSection").style.display="none";

}

// ======================================================
// ACTIVITY
// ======================================================

async function loadActivity(){

const res=await fetch("/get_activity");

const data=await res.json();

const body=document.querySelector("#activityTable tbody");

body.innerHTML="";

data.forEach(item=>{

body.innerHTML+=`

<tr>

<td>${item.name}</td>

<td>${item.student_id}</td>

<td>${item.question_answered}</td>

<td>${item.correct}</td>

<td>${item.wrong}</td>

<td>${item.skipped}</td>

<td>${item.violation_type||"-"}</td>

<td>${item.violation_count||0}</td>

<td>

${item.status=="Disqualified"

?'<span style="color:red;font-weight:bold;">Disqualified</span>'

:'Completed'}

</td>

<td>${item.last_violation||"-"}</td>

</tr>

`;

});

}

// ======================================================
// SCOREBOARD
// ======================================================

async function loadScore(){

const res=await fetch("/get_scores");

const data=await res.json();

const body=document.querySelector("#scoreTable tbody");

body.innerHTML="";

data.forEach((item,index)=>{

body.innerHTML+=`

<tr>

<td>${index+1}</td>

<td>${item.name}</td>

<td>${item.student_id}</td>

<td>${item.correct}</td>

<td>${item.wrong}</td>

<td>${item.result}</td>

<td>${item.badge}</td>

</tr>

`;

});

}

// ======================================================
// AUTO REFRESH
// ======================================================

setInterval(()=>{

if(document.getElementById("activityPanel").style.display=="block"){

loadActivity();

}

if(document.getElementById("scorePanel").style.display=="block"){

loadScore();

}

},5000);
