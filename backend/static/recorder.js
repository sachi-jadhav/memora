document.addEventListener("DOMContentLoaded", () => {
  console.log("Recorder JS loaded");

  const socket = io();

  const startBtn = document.getElementById("startBtn");
  const stopBtn = document.getElementById("stopBtn");
  const statusPill = document.getElementById("status");
  const timerEl = document.getElementById("timer");

  const transcriptBox = document.getElementById("transcriptBox");
  const summaryBox = document.getElementById("summaryBox");
  const actionBox = document.getElementById("actionBox");

  if (!startBtn || !stopBtn) {
    console.error("Buttons not found in DOM");
    return;
  }

  let recorder;
  let stream;
  let seconds = 0;
  let timerInterval;

  function startTimer() {
    timerInterval = setInterval(() => {
      seconds++;
      const h = String(Math.floor(seconds / 3600)).padStart(2, "0");
      const m = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
      const s = String(seconds % 60).padStart(2, "0");
      timerEl.innerText = `${h}:${m}:${s}`;
    }, 1000);
  }

  function stopTimer() {
    clearInterval(timerInterval);
  }

  socket.on("transcript", data => {
    const placeholder = transcriptBox.querySelector(".placeholder");
    if (placeholder) placeholder.remove();

    const p = document.createElement("p");
    p.textContent = data.text;
    transcriptBox.appendChild(p);
    transcriptBox.scrollTop = transcriptBox.scrollHeight;
  });

  socket.on("mom_generated", data => {
    summaryBox.innerText = data.summary || "No summary generated.";

    actionBox.innerHTML = "";
    (data.actions || []).forEach(a => {
      const li = document.createElement("li");
      li.textContent = a;
      actionBox.appendChild(li);
    });

    statusPill.innerText = "Completed";
    statusPill.classList.remove("recording");
  });

  startBtn.onclick = async () => {
    console.log("Start clicked");

    if (!navigator.mediaDevices) {
      alert("Media devices not supported");
      return;
    }

    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      console.error("Mic permission error:", err);
      alert("Microphone permission denied");
      return;
    }

    recorder = new MediaRecorder(stream);

    recorder.ondataavailable = e => {
      socket.emit("audio_chunk", e.data);
    };

    recorder.start(1000);

    seconds = 0;
    startTimer();

    startBtn.disabled = true;
    stopBtn.disabled = false;

    statusPill.innerText = "Recording";
    statusPill.classList.add("recording");
  };

  stopBtn.onclick = () => {
    console.log("Stop clicked");

    if (!recorder) return;

    recorder.stop();
    stream.getTracks().forEach(t => t.stop());

    stopTimer();
    socket.emit("end_meeting");

    startBtn.disabled = false;
    stopBtn.disabled = true;

    statusPill.innerText = "Generating MoM…";
    statusPill.classList.remove("recording");
  };
});
