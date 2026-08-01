const coreContainer = document.getElementById('core-container');
const statusText = document.getElementById('status-text');
const transcriptText = document.getElementById('transcript-text');

let ws;
let currentAudio = null;
let isAwake = false;
let isProcessing = false;
let fullCommand = "";

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const recognition = new SpeechRecognition();
recognition.continuous = true;
recognition.interimResults = true;
recognition.lang = 'en-US';

const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${wsProtocol}//${window.location.host}/ws`;

function connectWebSocket() {
    ws = new WebSocket(WS_URL);
    
    ws.onopen = () => {
        statusText.innerText = "SYSTEM ONLINE";
        coreContainer.className = "jarvis-container state-idle";
        // Start continuous background listening once connected
        recognition.start();
    };

    ws.onmessage = async (event) => {
        if (typeof event.data === "string") {
            const data = JSON.parse(event.data);
            if (data.type === "response_text") {
                transcriptText.innerText = `Ultron: ${data.text}`;
            }
        } else {
            // Play audio response
            coreContainer.className = "jarvis-container state-speaking";
            statusText.innerText = "RESPONDING";
            
            const audioBlob = new Blob([event.data], { type: 'audio/mp3' });
            const audioUrl = URL.createObjectURL(audioBlob);
            
            if (currentAudio) currentAudio.pause();
            
            currentAudio = new Audio(audioUrl);
            currentAudio.onended = () => {
                coreContainer.className = "jarvis-container state-idle";
                statusText.innerText = "AWAITING INPUT";
                isProcessing = false;
                isAwake = false; // Reset to require wake word again
                fullCommand = "";
            };
            await currentAudio.play();
        }
    };

    ws.onclose = () => {
        statusText.innerText = "CONNECTION LOST. RECONNECTING...";
        setTimeout(connectWebSocket, 3000);
    };
}

let silenceTimer = null;

recognition.onresult = (event) => {
    if (isProcessing) return; // Ignore input while he is thinking/speaking

    let interimTranscript = "";
    let finalTranscriptThisChunk = "";

    for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
            finalTranscriptThisChunk += event.results[i][0].transcript + " ";
        } else {
            interimTranscript += event.results[i][0].transcript;
        }
    }

    let liveDisplay = (fullCommand + finalTranscriptThisChunk + interimTranscript).trim().toLowerCase();
    
    if (liveDisplay) {
         transcriptText.innerText = `You: ${liveDisplay}`;
    }

    // Wake Word Detection
    if (!isAwake && liveDisplay.includes("ultron")) {
        isAwake = true;
        coreContainer.className = "jarvis-container state-listening";
        statusText.innerText = "LISTENING...";
        // Strip the wake word so it's not part of the command
        fullCommand = liveDisplay.substring(liveDisplay.indexOf("ultron") + 6).trim();
    } else if (isAwake) {
        fullCommand += finalTranscriptThisChunk;
        
        // If he is awake and you stop speaking for 1.5 seconds, send the command!
        clearTimeout(silenceTimer);
        silenceTimer = setTimeout(() => {
            let finalCommand = (fullCommand + interimTranscript).trim();
            if (finalCommand.length > 0 && ws && ws.readyState === WebSocket.OPEN) {
                isProcessing = true;
                coreContainer.className = "jarvis-container state-processing";
                statusText.innerText = "PROCESSING";
                
                // Send TEXT via websocket instead of audio for faster processing
                ws.send(JSON.stringify({ type: "text_query", text: finalCommand }));
            }
        }, 1500); 
    }
};

recognition.onend = () => {
    // Keep it running forever
    if (!isProcessing) {
        recognition.start();
    }
};

recognition.onerror = (e) => {
    console.log("Speech recognition error:", e.error);
    if (e.error === 'not-allowed') {
        alert("Please allow microphone access in Chrome settings.");
    }
};

// Start connection
connectWebSocket();
