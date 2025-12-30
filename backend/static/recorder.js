const socket = io("http://127.0.0.1:5000");

// UI Elements
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const statusText = document.getElementById("status");
const transcriptBox = document.getElementById("transcriptBox");
const summaryBox = document.getElementById("summaryBox");
const actionBox = document.getElementById("actionBox");
const timerDisplay = document.getElementById("timer");

// Media + State
let mediaRecorder = null;
let audioStream = null;
let isRecording = false;
let timerInterval = null;
let elapsedSeconds = 0;
let chunkInterval = null;
let timerStarted = false;

/* -----------------------------
   RESET UI FOR NEW MEETING
------------------------------ */
function resetUIForNewMeeting() {
  transcriptBox.innerHTML = `
    <p class="placeholder">
      🎙️ Live transcript will appear here once recording starts.
    </p>
  `;

  summaryBox.innerText = "Summary will be generated after the meeting ends.";
  actionBox.innerHTML = `<li class="placeholder">Action items will appear here.</li>`;

  elapsedSeconds = 0;
  updateTimerDisplay();
}

/* -----------------------------
   START MEETING
------------------------------ */
startBtn.onclick = async () => {
  if (isRecording) return;

  // 🔑 Clear previous meeting visually
  resetUIForNewMeeting();

  try {
    audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(audioStream);

    mediaRecorder.onstart = () => {
      isRecording = true;
      updateStatus("Recording", true);

      startBtn.disabled = true;
      stopBtn.disabled = false;

      if (!timerStarted) {
        startTimer();
        timerStarted = true;
      }
    };

    mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        socket.emit("audio_chunk", event.data);
      }
    };

    mediaRecorder.start();

    // 🔁 Restart every 5s to ensure valid WebM chunks
    chunkInterval = setInterval(() => {
      if (mediaRecorder.state === "recording") {
        mediaRecorder.stop();
        mediaRecorder.start();
      }
    }, 5000);

  } catch (err) {
    alert("Microphone permission is required.");
    console.error(err);
  }
};

/* -----------------------------
   END MEETING
------------------------------ */
stopBtn.onclick = () => {
  if (!mediaRecorder) return;

  isRecording = false;

  clearInterval(chunkInterval);
  chunkInterval = null;

  if (mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }

  if (audioStream) {
    audioStream.getTracks().forEach(track => track.stop());
  }

  stopTimer();
  timerStarted = false;

  updateStatus("Processing…", false);
  startBtn.disabled = false;
  stopBtn.disabled = true;

  summaryBox.innerText = "⏳ Generating summary...";
  actionBox.innerHTML = "";

  socket.emit("end_meeting");
};

/* -----------------------------
   TIMER
------------------------------ */
function startTimer() {
  elapsedSeconds = 0;
  updateTimerDisplay();

  timerInterval = setInterval(() => {
    elapsedSeconds++;
    updateTimerDisplay();
  }, 1000);
}

function stopTimer() {
  clearInterval(timerInterval);
  timerInterval = null;
}

function updateTimerDisplay() {
  const hrs = String(Math.floor(elapsedSeconds / 3600)).padStart(2, "0");
  const mins = String(Math.floor((elapsedSeconds % 3600) / 60)).padStart(2, "0");
  const secs = String(elapsedSeconds % 60).padStart(2, "0");
  timerDisplay.innerText = `${hrs}:${mins}:${secs}`;
}

/* -----------------------------
   STATUS
------------------------------ */
function updateStatus(text, recording) {
  statusText.innerText = text;
  statusText.classList.toggle("recording", recording);
}

/* -----------------------------
   SOCKET LISTENERS
------------------------------ */
socket.on("transcript", (data) => {
  const placeholder = transcriptBox.querySelector(".placeholder");
  if (placeholder) transcriptBox.innerHTML = "";

  const p = document.createElement("p");
  p.textContent = data.text;
  transcriptBox.appendChild(p);
  transcriptBox.scrollTop = transcriptBox.scrollHeight;
});

socket.on("mom_generated", (data) => {
  summaryBox.innerText = data.summary || "No summary generated.";

  actionBox.innerHTML = "";
  if (!data.actions || data.actions.length === 0) {
    actionBox.innerHTML = "<li>No action items detected.</li>";
  } else {
    data.actions.forEach(action => {
      const li = document.createElement("li");
      li.textContent = action;
      actionBox.appendChild(li);
    });
  }

  updateStatus("Saved", false);
});
