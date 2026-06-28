// =======================================================
// PQDS QUIZ ENGINE
// =======================================================

let questions = [];
let current = 0;
let answers = {};

let timerInterval = null;
let submitted = false;
let fullscreenWarning = false;
let violationCooldown = false;

let violations = [];

const MAX_WARNINGS = 2;

window.onload = initializeQuiz;

// =======================================================
// INITIALIZE
// =======================================================

async function initializeQuiz(){

    await loadQuiz();

    registerProctorEvents();

}


// =======================================================
// LOAD QUIZ
// =======================================================

async function loadQuiz(){

    const quizId = window.location.pathname.split("/").pop();

    //----------------------------------------------------
    // Fetch Quiz
    //----------------------------------------------------

    const quizResponse = await fetch("/get_quiz/" + quizId);

    const quiz = await quizResponse.json();

    if(!quiz){

        alert("Quiz not found");

        location.href="/student";

        return;

    }

    document.getElementById("quizTitle").innerHTML = quiz.title;


    //----------------------------------------------------
    // Time Validation
    //----------------------------------------------------

    const now = new Date();

    const start = new Date(quiz.start_time);

    const end = new Date(quiz.end_time);


    if(now < start){

        alert("Quiz has not started yet.");

        location.href="/student";

        return;

    }

    if(now > end){

        alert("Quiz expired.");

        location.href="/student";

        return;

    }


    //----------------------------------------------------
    // Check Already Attempted
    //----------------------------------------------------

    const check = await fetch("/check_attempt/"+quizId);

    const attempt = await check.json();

    if(attempt.attempted){

        alert("You already attended this quiz.");

        location.href="/student";

        return;

    }


    //----------------------------------------------------
    // Questions
    //----------------------------------------------------

    const qRes = await fetch("/get_questions/"+quizId);

    questions = await qRes.json();

    if(!questions.length){

        alert("No questions uploaded.");

        location.href="/student";

        return;

    }

    renderQuestion();

    startRealtimeTimer(quiz.end_time);

    enterFullscreen();

}


// =======================================================
// FULLSCREEN
// =======================================================

async function enterFullscreen(){

    try{

        const el=document.documentElement;

        if(el.requestFullscreen){

            await el.requestFullscreen();

        }

    }

    catch(e){

        console.log(e);

    }

}
// =======================================================
// RENDER QUESTION
// =======================================================

function renderQuestion(){

    const q = questions[current];

    document.getElementById("questionText").innerHTML =
        `${current + 1}. ${q.question}`;

    let html = '<div class="options-grid">';

    q.options.forEach(option=>{

        const checked = answers[current]===option ? "checked":"";
        const selected = answers[current]===option ? "selected":"";

        html += `

        <label class="option-card ${selected}">

            <input
                type="radio"
                name="option"
                value="${option}"
                ${checked}
                onchange="selectAnswer('${option.replace(/'/g,"\\'")}')">

            <span>${option}</span>

        </label>

        `;

    });

    html += "</div>";

    document.getElementById("optionsBox").innerHTML = html;


    //---------------------------------------------------
    // Navigation Buttons
    //---------------------------------------------------

    document.getElementById("prevBtn").style.display =
        current===0 ? "none":"inline-block";

    document.getElementById("nextBtn").style.display =
        current===questions.length-1 ? "none":"inline-block";

    document.getElementById("submitBtn").style.display =
        current===questions.length-1 ? "inline-block":"none";


    //---------------------------------------------------
    // Progress Indicator (optional)
    //---------------------------------------------------

    document.title =
        `Question ${current+1}/${questions.length}`;

}



// =======================================================
// SELECT ANSWER
// =======================================================

function selectAnswer(value){

    answers[current]=value;

    document
    .querySelectorAll(".option-card")
    .forEach(card=>{

        card.classList.remove("selected");

        const input = card.querySelector("input");

        if(input.value===value){

            card.classList.add("selected");

        }

    });

}



// =======================================================
// NEXT
// =======================================================

function nextQuestion(){

    if(current>=questions.length-1){

        return;

    }

    current++;

    renderQuestion();

}



// =======================================================
// PREVIOUS
// =======================================================

function prevQuestion(){

    if(current<=0){

        return;

    }

    current--;

    renderQuestion();

}



// =======================================================
// JUMP QUESTION
// =======================================================

function jumpQuestion(index){

    if(index<0) return;

    if(index>=questions.length) return;

    current=index;

    renderQuestion();

}



// =======================================================
// ANSWER COUNT
// =======================================================

function answeredCount(){

    return Object.keys(answers).length;

}



// =======================================================
// UNANSWERED COUNT
// =======================================================

function unansweredCount(){

    return questions.length-answeredCount();

}



// =======================================================
// SAVE STATE (Optional)
// =======================================================

function saveProgress(){

    localStorage.setItem(

        "quiz_answers",

        JSON.stringify(answers)

    );

}



// =======================================================
// RESTORE STATE
// =======================================================

function restoreProgress(){

    const saved = localStorage.getItem("quiz_answers");

    if(saved){

        answers = JSON.parse(saved);

    }

}



// =======================================================
// AUTO SAVE EVERY 10 SECONDS
// =======================================================

setInterval(()=>{

    if(!submitted){

        saveProgress();

    }

},10000);



// =======================================================
// BEFORE LEAVING PAGE
// =======================================================

window.addEventListener("beforeunload",(e)=>{

    if(submitted) return;

    e.preventDefault();

    e.returnValue="";

});

// =======================================================
// REALTIME TIMER
// =======================================================

function startRealtimeTimer(endTime){

    clearInterval(timerInterval);

    timerInterval = setInterval(()=>{

        const now = new Date();

        const end = new Date(endTime);

        const diff = Math.floor((end-now)/1000);

        if(diff<=0){

            clearInterval(timerInterval);

            document.getElementById("timer").innerHTML="00:00";

            autoSubmit();

            return;

        }

        const mins = Math.floor(diff/60);

        const secs = diff%60;

        document.getElementById("timer").innerHTML=

        `${String(mins).padStart(2,"0")}:${String(secs).padStart(2,"0")}`;

    },1000);

}



// =======================================================
// CONFIRM SUBMIT
// =======================================================

function confirmSubmit(){

    if(submitted) return;

    const unanswered = unansweredCount();

    let message="";

    if(unanswered>0){

        message=

        `You still have ${unanswered} unanswered question(s).\n\nSubmit anyway?`;

    }

    else{

        message="Submit quiz? You cannot change answers afterwards.";

    }

    if(confirm(message)){

        submitQuiz();

    }

}



// =======================================================
// AUTO SUBMIT
// =======================================================

function autoSubmit(){

    if(submitted) return;

    alert("⏰ Time is over.\nQuiz will be submitted automatically.");

    submitQuiz();

}



// =======================================================
// CALCULATE SCORE
// =======================================================

function calculateResult(){

    let correct=0;

    let wrong=0;

    let skipped=0;

    questions.forEach((q,index)=>{

        const ans=answers[index];

        if(!ans){

            skipped++;

            return;

        }

        const correctAnswer=

            q.options[

                ["A","B","C","D"]

                .indexOf(q.answer.toUpperCase())

            ];

        if(ans===correctAnswer){

            correct++;

        }

        else{

            wrong++;

        }

    });

    return{

        correct,

        wrong,

        skipped

    };

}



// =======================================================
// SUBMIT QUIZ
// =======================================================

async function submitQuiz(){

    if(submitted) return;

    submitted=true;

    clearInterval(timerInterval);

    const submitBtn=document.getElementById("submitBtn");

    if(submitBtn){

        submitBtn.disabled=true;

        submitBtn.innerHTML="Submitting...";

    }

    const quizId=

        window.location.pathname.split("/").pop();

    const result=

        calculateResult();

    try{

        const response=

        await fetch("/submit_quiz",{

            method:"POST",

            headers:{

                "Content-Type":"application/json"

            },

            body:JSON.stringify({

                quiz_id:quizId,

                correct:result.correct,

                wrong:result.wrong,

                skipped:result.skipped,

                violations:violations

            })

        });

        const data=await response.json();

        console.log(data);

        clearLocalQuiz();

        alert("✅ Quiz Submitted Successfully.");

        window.location.href="/student";

    }

    catch(err){

        console.error(err);

        alert("Submission failed.\nPlease try again.");

        submitted=false;

    }

}



// =======================================================
// CLEAR STORAGE
// =======================================================

function clearLocalQuiz(){

    localStorage.removeItem("quiz_answers");

}



// =======================================================
// NETWORK DETECT
// =======================================================

window.addEventListener("offline",()=>{

    alert("⚠ Internet connection lost.\nReconnect immediately.");

});



window.addEventListener("online",()=>{

    console.log("Internet Restored");

});



// =======================================================
// DISABLE DOUBLE SUBMIT
// =======================================================

document.addEventListener("keydown",(e)=>{

    if(e.key==="Enter"){

        if(submitted){

            e.preventDefault();

        }

    }

});
// =======================================================
// PROCTORING ENGINE
// =======================================================

let violationCount = 0;

function registerProctorEvents(){

    // Tab Change
    document.addEventListener("visibilitychange", handleVisibility);

    // Window Blur
    window.addEventListener("blur", handleBlur);

    // Fullscreen Exit
    document.addEventListener("fullscreenchange", handleFullscreen);

    // Disable Right Click
    document.addEventListener("contextmenu", blockRightClick);

    // Keyboard Shortcuts
    document.addEventListener("keydown", blockKeys);

    // Copy Cut Paste
    document.addEventListener("copy", blockCopy);

    document.addEventListener("cut", blockCut);

    document.addEventListener("paste", blockPaste);

}



// =======================================================
// LOG VIOLATION
// =======================================================

async function logViolation(type){

    if(submitted) return;

    if(violationCooldown) return;

    violationCooldown = true;

    setTimeout(()=>{

        violationCooldown=false;

    },2500);


    const time=new Date().toLocaleString();

    violations.push({

        type:type,

        time:time

    });

    try{

        const quizId=window.location.pathname.split("/").pop();

        const response=await fetch("/log_violation",{

            method:"POST",

            headers:{

                "Content-Type":"application/json"

            },

            body:JSON.stringify({

                quiz_id:quizId,

                violation_type:type,

                timestamp:time

            })

        });

        const result=await response.json();

        violationCount=result.violation_count || violationCount+1;

        if(result.disqualified){

            alert(

                "🚫 You have exceeded the allowed violations.\n\nQuiz terminated."

            );

            submitted=true;

            location.href="/student";

            return;

        }

        alert(

            "⚠ Warning ("+

            violationCount+

            "/2)\n\n"+

            type

        );

    }

    catch(e){

        console.log(e);

    }

}



// =======================================================
// TAB SWITCH
// =======================================================

function handleVisibility(){

    if(document.hidden){

        logViolation("Tab Switch / Window Minimized");

    }

}



// =======================================================
// WINDOW BLUR
// =======================================================

function handleBlur(){

    logViolation("Window Lost Focus");

}



// =======================================================
// FULLSCREEN EXIT
// =======================================================

function handleFullscreen(){

    if(submitted) return;

    if(!document.fullscreenElement){

        logViolation("Exited Fullscreen");

        setTimeout(()=>{

            enterFullscreen();

        },1000);

    }

}



// =======================================================
// RIGHT CLICK
// =======================================================

function blockRightClick(e){

    e.preventDefault();

    logViolation("Right Click Attempt");

}



// =======================================================
// COPY
// =======================================================

function blockCopy(e){

    e.preventDefault();

    logViolation("Copy Attempt");

}



// =======================================================
// CUT
// =======================================================

function blockCut(e){

    e.preventDefault();

    logViolation("Cut Attempt");

}



// =======================================================
// PASTE
// =======================================================

function blockPaste(e){

    e.preventDefault();

    logViolation("Paste Attempt");

}



// =======================================================
// KEYBOARD SHORTCUT BLOCKER
// =======================================================

function blockKeys(e){

    // F12
    if(e.key==="F12"){

        e.preventDefault();

        logViolation("Developer Tools");

        return;

    }

    // Ctrl combinations

    if(e.ctrlKey){

        const blocked=[

            "c",

            "v",

            "x",

            "u",

            "s",

            "p",

            "a"

        ];

        if(

            blocked.includes(

                e.key.toLowerCase()

            )

        ){

            e.preventDefault();

            logViolation(

                "Blocked Shortcut : Ctrl+"+

                e.key.toUpperCase()

            );

            return;

        }

    }

    // Ctrl Shift combinations

    if(

        e.ctrlKey &&

        e.shiftKey &&

        ["I","J","C"]

        .includes(e.key.toUpperCase())

    ){

        e.preventDefault();

        logViolation(

            "Developer Shortcut"

        );

    }

}
