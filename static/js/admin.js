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

console.log("Sending Questions:", questions)



// ================= QR GENERATION =================

function generateQR(quizId, title, duration){



let url = window.location.origin + "/join/" + quizId



// clear previous QR

document.getElementById("qrCanvas").innerHTML = ""



// 🔥 CREATE PREMIUM QR

const qr = new QRCodeStyling({



    width: 220,

    height: 220,

    type: "svg",

    data: url,



    // 🎯 DOT STYLE

    dotsOptions: {

        color: "#111827",

        type: "rounded"   // 🔥 rounded dots

    },



    // 🧱 CORNER (EYES)

    cornersSquareOptions: {

        type: "extra-rounded",  // 🔥 rounded squares

        color: "#111827"

    },



    cornersDotOptions: {

        type: "dot",  // 🔥 inner eye dot

        color: "#111827"

    },



    // 🎨 BACKGROUND

    backgroundOptions: {

        color: "#ffffff"

    },



    // 🖼 LOGO

    image: "/static/images/logo.png",

    imageOptions: {

        crossOrigin: "anonymous",

        margin: 6

    },



    // 🔐 ERROR CORRECTION

    qrOptions: {

        errorCorrectionLevel: "H"

    }



})



// append QR

qr.append(document.getElementById("qrCanvas"))



// SET DETAILS

document.getElementById("qrId").innerText = quizId

document.getElementById("qrTitle").innerText = title

document.getElementById("qrDetails").innerText = "Duration: " + duration + " mins"



// SHOW CARD

document.getElementById("qrSection").style.display = "block"



// store globally for download

window.qrInstance = qr



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



if(window.qrInstance){



    window.qrInstance.download({

        name: "quiz_qr",

        extension: "png"

    })



}



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



try {

    let res=await fetch("/upload_questions",{

    method:"POST",

    body:formData

    })



    let data;

    try {

        data = await res.json()

    } catch (e) {

        alert("Upload failed: Invalid server response.")

        return

    }



    if (data && data.error) {

        alert("Error: " + data.error)

        return

    }



    if(!Array.isArray(data)){

    alert("Invalid format: Expected an array of questions.")

    return

    }



    questions = data.filter(q => 

        q.question && 

        Array.isArray(q.options) && 

        q.options.length === 4 && 

        q.answer

    )



    if(questions.length === 0){

        alert("No valid questions found in file structure.")

        return

    }



    alert(questions.length + " Valid Questions Uploaded")

} catch (err) {

    alert("An error occurred during file upload: " + err.message)

}

}


// ================= ACTIVITY =================

async function loadActivity() {

    showPanel("activityPanel");

    try {

        const res = await fetch("/get_activity");
        const data = await res.json();

        const table = document.querySelector("#activityTable tbody");
        table.innerHTML = "";

        if (!Array.isArray(data) || data.length === 0) {
            table.innerHTML = `
            <tr>
                <td colspan="10" style="text-align:center;">
                    No Activity Found
                </td>
            </tr>`;
            return;
        }

        data.forEach(item => {

            table.innerHTML += `
            <tr>

                <td>${item.name || "-"}</td>

                <td>${item.student_id || "-"}</td>

                <td>${item.question_answered ?? 0}</td>

                <td>${item.correct ?? 0}</td>

                <td>${item.wrong ?? 0}</td>

                <td>${item.skipped ?? 0}</td>

                <td>${item.violation_type || "-"}</td>

                <td>${item.violation_count ?? 0}</td>

                <td>
                    ${
                        item.status === "Disqualified"
                        ? "🚫 Disqualified"
                        : "✅ Active"
                    }
                </td>

                <td>${item.last_violation || "-"}</td>

            </tr>`;
        });

    } catch (err) {

        console.error(err);

        alert("Unable to load activity.");

    }

}

// ================= SCORE =================

async function loadScore() {

    showPanel("scorePanel");

    try {

        const res = await fetch("/get_scores");
        const data = await res.json();

        const table = document.querySelector("#scoreTable tbody");
        table.innerHTML = "";

        if (!Array.isArray(data) || data.length === 0) {

            table.innerHTML = `
            <tr>
                <td colspan="7" style="text-align:center;">
                    No Scores Available
                </td>
            </tr>`;

            return;

        }

        data.sort((a,b)=>b.correct-a.correct);

        data.forEach((item,index)=>{

            let badge="🥉";

            if(index===0) badge="🥇";
            else if(index===1) badge="🥈";
            else if(index>2) badge="Bronze";

            table.innerHTML+=`

            <tr>

                <td>${index+1}</td>

                <td>${item.name||"-"}</td>

                <td>${item.student_id||"-"}</td>

                <td>${item.correct??0}</td>

                <td>${item.wrong??0}</td>

                <td>${item.result||"-"}</td>

                <td>${badge}</td>

            </tr>

            `;

        });

    }

    catch(err){

        console.error(err);

        alert("Unable to load scores.");

    }

}
