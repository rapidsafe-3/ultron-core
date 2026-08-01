const coreContainer = document.getElementById('core-container');
const statusText = document.getElementById('status-text');
const transcriptText = document.getElementById('transcript-text');
const micBtn = document.getElementById('mic-btn');

let ws;
let mediaRecorder;
let audioChunks = [];
let currentAudio = null;

// Use wss:// for Render (secure websocket)
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${wsProtocol}//${window.location.host}/ws`;

function connectWebSocket() {
    ws = new WebSocket(WS_URL);
    
    ws.onopen = () => {
        statusText.innerText = "SYSTEM ONLINE";
        coreContainer.className = "jarvis-container state-idle";
    };

    ws.onmessage = async (event) => {
        if (typeof event.data === "string") {
            const data = JSON.parse(event.data);
            if (data.type === "transcript") {
                transcriptText.innerText = `You: ${data.text}`;
            } else if (data.type === "response_text") {
                transcriptText.innerText = `Ultron: ${data.text}`;
            }
        } else {
            // Received MP3 Bytes! Play instantly.
            coreContainer.className = "jarvis-container state-speaking";
            statusText.innerText = "RESPONDING";
            
            const audioBlob = new Blob([event.data], { type: 'audio/mp3' });
            const audioUrl = URL.createObjectURL(audioBlob);
            
            if (currentAudio) { currentAudio.pause(); }
            
            currentAudio = new Audio(audioUrl);
            currentAudio.onended = () => {
                coreContainer.className = "jarvis-container state-idle";
                statusText.innerText = "AWAITING INPUT";
            };
            currentAudio.play();
        }
    };

    ws.onclose = () => {
        statusText.innerText = "CONNECTION LOST. RECONNECTING...";
        setTimeout(connectWebSocket, 3000);
    };
}

// Push-to-Talk Logic (Highest Reliability for Mobile)
micBtn.addEventListener('touchstart', startRecording, {passive: true});
micBtn.addEventListener('touchend', stopRecording);
micBtn.addEventListener('mousedown', startRecording);
micBtn.addEventListener('mouseup', stopRecording);

async function startRecording(e) {
    if(e) e.preventDefault();
    if (currentAudio) currentAudio.pause(); // Interrupt speaking immediately
    
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
        mediaRecorder.onstop = () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(audioBlob); // Send audio instantly over socket!
                coreContainer.className = "jarvis-container state-processing";
                statusText.innerText = "PROCESSING";
            }
            stream.getTracks().forEach(track => track.stop());
        };

        mediaRecorder.start();
        coreContainer.className = "jarvis-container state-listening";
        statusText.innerText = "LISTENING...";
    } catch (err) {
        alert("Microphone permission denied.");
    }
}

function stopRecording(e) {
    if(e) e.preventDefault();
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
}

// Initialize
connectWebSocket();
