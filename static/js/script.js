// ================= SPINNER REDIRECT =================
document.addEventListener("DOMContentLoaded", function() {
    const spinnerRedirect = document.querySelector(".spinner-container");

    if(spinnerRedirect) {
        setTimeout(() => {
            window.location.href = "/login";
        }, 2000); // 2 seconds
    }
});


// ================= AUTO ROLE DETECTION HINT =================
const emailInput = document.querySelector('input[name="email"]');

if(emailInput){
    emailInput.addEventListener('input', function() {

        const val = emailInput.value.toLowerCase();
        const roleHint = document.getElementById('role-hint');

        if(roleHint){

            if(/^[a-z0-9]+@bhc\.professor\.com$/.test(val)) {
                roleHint.textContent = "Detected role: Teacher";
            }

            else if(/^[a-z0-9]+@bhc\.student\.com$/.test(val)) {
                roleHint.textContent = "Detected role: Student";
            }

            else {
                roleHint.textContent = "";
            }

        }
    });
}



// ================= SPLASH SCREEN HIDE =================
window.addEventListener("load", () => {
  const splash = document.getElementById("splash");

  setTimeout(() => {
    splash.style.opacity = "0";
    setTimeout(() => splash.remove(), 800);
  }, 1500);
});
// 🚫 BLOCK CTRL + SCROLL ZOOM (safe)
window.addEventListener("wheel", function(e){
  if(e.ctrlKey){
    e.preventDefault()
  }
}, { passive:false })

// 🚫 BLOCK KEYBOARD ZOOM
document.addEventListener("keydown", function(e){
  if(e.ctrlKey && ["+","-","="].includes(e.key)){
    e.preventDefault()
  }
})

// ✅ DO NOT FORCE HARD ZOOM (remove this line ❌)
// document.body.style.zoom = "100%"

// ✅ Instead use this:
document.documentElement.style.zoom = "1"