const BACKEND_URL = "/chat";
const WAKE_WORD = "ultron";
const SHUTDOWN_COMMANDS = ["shut down", "go to sleep", "sleep", "turn off", "power down", "bye"];

const core = document.getElementById('ultron-core');
const statusText = document.getElementById('status-text');
const transcriptDisplay = document.getElementById('transcript-display');
const initBtn = document.getElementById('init-btn');

let isAwake = false;
let isProcessing = false;
let isSpeaking = false;

let speechSilenceTimer = null;
let fullSpeechBuffer = "";

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const synth = window.speechSynthesis;

if (!SpeechRecognition) {
    statusText.innerText = "BROWSER UNSUPPORTED";
    transcriptDisplay.innerText = "Please open directly in Google Chrome.";
}

const recognition = new SpeechRecognition();
recognition.continuous = true;
recognition.interimResults = true;
recognition.lang = 'en-US';

function setCoreState(stateClass, text) {
    core.className = stateClass;
    statusText.innerText = text;
}

function getNaturalVoice() {
    const voices = synth.getVoices();
    return voices.find(v => 
        v.name.includes("Google US English") || 
        v.name.includes("Natural") || 
        v.name.includes("Enhanced") || 
        (v.lang === "en-US" && !v.name.includes("Network"))
    ) || voices[0];
}

function speak(text, shouldShutdown = false) {
    isSpeaking = true;
    setCoreState('core-speaking', 'ULTRON');
    
    // Clean text of markdown formatting for natural voice output
    const cleanText = text.replace(/[*_#`]/g, '');
    const utterance = new SpeechSynthesisUtterance(cleanText);
    
    const preferredVoice = getNaturalVoice();
    if (preferredVoice) utterance.voice = preferredVoice;

    utterance.pitch = 1.0; 
    utterance.rate = 1.05; // Slightly conversational speed

    utterance.onend = () => {
        isSpeaking = false;
        fullSpeechBuffer = "";
        
        if (shouldShutdown) {
            isAwake = false;
            isProcessing = false;
            setCoreState('core-idle', 'STANDBY');
            transcriptDisplay.innerText = `Say "${WAKE_WORD.toUpperCase()}" to activate`;
        } else {
            isProcessing = false;
            setCoreState('core-listening', 'LISTENING');
            transcriptDisplay.innerText = "Listening...";
        }
    };

    synth.speak(utterance);
}

// Function to send complete speech to backend
async function sendToBackend(messageText) {
    if (isProcessing || !messageText.trim()) return;

    isProcessing = true;
    setCoreState('core-processing', 'THINKING');

    try {
        const response = await fetch(BACKEND_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: messageText })
        });

        if (!response.ok) throw new Error("Backend error");

        const data = await response.json();
        speak(data.response, false);

    } catch (error) {
        console.error(error);
        speak("I ran into an issue connecting to core services. Let me try again.", false);
    }
}

recognition.onresult = (event) => {
    if (isSpeaking) return;

    let interimTranscript = "";
    let finalTranscriptThisChunk = "";

    for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
            finalTranscriptThisChunk += event.results[i][0].transcript + " ";
        } else {
            interimTranscript += event.results[i][0].transcript;
        }
    }

    if (finalTranscriptThisChunk) {
        fullSpeechBuffer += finalTranscriptThisChunk;
    }

    let liveDisplay = (fullSpeechBuffer + interimTranscript).trim().toLowerCase();
    if (liveDisplay) {
        transcriptDisplay.innerText = `"${liveDisplay}"`;
    }

    // 1. Activation Check
    if (!isAwake) {
        if (liveDisplay.includes(WAKE_WORD)) {
            isAwake = true;
            fullSpeechBuffer = "";
            speak("Hey there! I'm awake. What's on your mind?");
        }
        return;
    }

    // 2. Shutdown Check
    const isShutdownReq = SHUTDOWN_COMMANDS.some(cmd => liveDisplay.includes(cmd));
    if (isAwake && isShutdownReq && !isProcessing) {
        isProcessing = true;
        fullSpeechBuffer = "";
        clearTimeout(speechSilenceTimer);
        speak("Going into standby mode. Catch you later!", true);
        return;
    }

    // 3. Smart Silence Buffer: Waits 1.8 seconds of complete silence before sending!
    if (isAwake && !isProcessing) {
        clearTimeout(speechSilenceTimer);
        speechSilenceTimer = setTimeout(() => {
            let completeMessage = (fullSpeechBuffer + interimTranscript).trim();
            // Remove wake word from message body if spoken
            completeMessage = completeMessage.replace(new RegExp(WAKE_WORD, "gi"), "").trim();

            if (completeMessage.length > 0) {
                fullSpeechBuffer = "";
                sendToBackend(completeMessage);
            }
        }, 1800); // 1.8 second delay ensures full sentence capture
    }
};

recognition.onerror = (e) => {
    if (e.error === 'not-allowed') {
        statusText.innerText = "MIC PERMISSION DENIED";
    }
};

recognition.onend = () => {
    try { recognition.start(); } catch (e) {}
};

if (speechSynthesis.onvoiceschanged !== undefined) {
    speechSynthesis.onvoiceschanged = getNaturalVoice;
}

initBtn.addEventListener('click', () => {
    try {
        recognition.start();
        initBtn.style.display = 'none';
        setCoreState('core-idle', 'STANDBY');
        transcriptDisplay.innerText = `Say "${WAKE_WORD.toUpperCase()}" to activate`;
    } catch (err) {
        alert("Please open this link directly in Google Chrome!");
    }
});
