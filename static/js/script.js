// =====================================================
// PQDS GLOBAL SCRIPT
// =====================================================

// ----------------------------
// Spinner Redirect
// ----------------------------
document.addEventListener("DOMContentLoaded", () => {

    const spinner = document.querySelector(".spinner-container");

    if (spinner) {
        setTimeout(() => {
            location.href = "/login";
        }, 2000);
    }

});


// ----------------------------
// Splash Screen
// ----------------------------
window.addEventListener("load", () => {

    const splash = document.getElementById("splash");

    if (!splash) return;

    setTimeout(() => {

        splash.style.opacity = "0";

        setTimeout(() => {

            splash.remove();

        },800);

    },1500);

});


// ----------------------------
// Auto Role Detection
// ----------------------------
document.addEventListener("DOMContentLoaded",()=>{

const email=document.querySelector('input[name="email"]');

if(!email) return;

const hint=document.getElementById("role-hint");

if(!hint) return;

email.addEventListener("input",()=>{

const value=email.value.toLowerCase();

if(/^[a-z0-9]+@bhc\.professor\.com$/.test(value))
hint.innerHTML="Detected Role : Professor";

else if(/^[a-z0-9]+@bhc\.student\.com$/.test(value))
hint.innerHTML="Detected Role : Student";

else
hint.innerHTML="";

});

});


// ----------------------------
// Disable Browser Zoom
// ----------------------------
window.addEventListener("wheel",(e)=>{

if(e.ctrlKey){

e.preventDefault();

}

},{passive:false});


document.addEventListener("keydown",(e)=>{

if(e.ctrlKey && ["=","+","-"].includes(e.key)){

e.preventDefault();

}

});

document.documentElement.style.zoom="1";


// =====================================================
// LOGOUT CONFIRMATION
// =====================================================

document.addEventListener("click",(e)=>{

const btn=e.target.closest("button");

if(!btn) return;

if(btn.textContent.trim().toLowerCase()=="logout"){

e.preventDefault();

const ok=confirm("Do you really want to logout?");

if(ok){

location.href="/logout";

}

}

});


// =====================================================
// INTERNET STATUS
// =====================================================

function networkStatus(){

if(navigator.onLine){

showToast("🟢 Connected","success");

}else{

showToast("🔴 Internet Disconnected","error");

}

}

window.addEventListener("online",networkStatus);

window.addEventListener("offline",networkStatus);


// =====================================================
// TOAST
// =====================================================

function showToast(message,type="success"){

let toast=document.getElementById("toast");

if(!toast){

toast=document.createElement("div");

toast.id="toast";

toast.style.position="fixed";
toast.style.top="20px";
toast.style.right="20px";
toast.style.padding="14px 22px";
toast.style.borderRadius="12px";
toast.style.color="white";
toast.style.fontWeight="600";
toast.style.zIndex="999999";
toast.style.transition=".3s";

document.body.appendChild(toast);

}

toast.innerHTML=message;

toast.style.background=

type=="error"
?"#dc2626"
:type=="warning"
?"#f59e0b"
:"#22c55e";

toast.style.opacity="1";

setTimeout(()=>{

toast.style.opacity="0";

},3000);

}


// =====================================================
// LOADING OVERLAY
// =====================================================

function showLoading(text="Processing..."){

let loader=document.getElementById("globalLoader");

if(loader) return;

loader=document.createElement("div");

loader.id="globalLoader";

loader.innerHTML=`

<div class="loader-card">

<div class="spinner"></div>

<p>${text}</p>

</div>

`;

loader.style.position="fixed";
loader.style.top="0";
loader.style.left="0";
loader.style.width="100%";
loader.style.height="100%";
loader.style.background="rgba(0,0,0,.55)";
loader.style.display="flex";
loader.style.alignItems="center";
loader.style.justifyContent="center";
loader.style.zIndex="999999";

document.body.appendChild(loader);

}


function hideLoading(){

const loader=document.getElementById("globalLoader");

if(loader){

loader.remove();

}

}


// =====================================================
// DISABLE BUTTONS DURING REQUEST
// =====================================================

function disableButtons(){

document.querySelectorAll("button").forEach(btn=>{

btn.disabled=true;

});

}

function enableButtons(){

document.querySelectorAll("button").forEach(btn=>{

btn.disabled=false;

});

}


// =====================================================
// SAFE FETCH
// =====================================================

async function api(url,options={}){

try{

showLoading();

disableButtons();

const response=await fetch(url,options);

const data=await response.json();

hideLoading();

enableButtons();

return data;

}

catch(err){

hideLoading();

enableButtons();

showToast("Server Error","error");

throw err;

}

}


// =====================================================
// DOUBLE CLICK PREVENTION
// =====================================================

document.addEventListener("click",(e)=>{

const btn=e.target.closest("button");

if(!btn) return;

if(btn.dataset.lock=="true"){

e.preventDefault();

return;

}

btn.dataset.lock="true";

setTimeout(()=>{

btn.dataset.lock="false";

},1200);

});


// =====================================================
// SESSION TIMEOUT WARNING
// =====================================================

let sessionTimer;

function resetSession(){

clearTimeout(sessionTimer);

sessionTimer=setTimeout(()=>{

showToast("Session expired. Login again.","warning");

setTimeout(()=>{

location.href="/logout";

},2000);

},1000*60*60);

}

["mousemove","keypress","click","scroll"].forEach(event=>{

document.addEventListener(event,resetSession);

});

resetSession();


// =====================================================
// COPY TO CLIPBOARD
// =====================================================

function copyText(text){

navigator.clipboard.writeText(text);

showToast("Copied");

}


// =====================================================
// GLOBAL ERROR HANDLER
// =====================================================

window.onerror=function(msg){

console.error(msg);

showToast("Unexpected Error","error");

};


// =====================================================
// PAGE READY
// =====================================================

document.addEventListener("DOMContentLoaded",()=>{

console.log("PQDS Loaded Successfully");

});
