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
    // Cancel any previous speech
    synth.cancel();
    
    isSpeaking = true;
    setCoreState('core-speaking', 'ULTRON');
    
    const cleanText = text.replace(/[*_#`]/g, '');
    const utterance = new SpeechSynthesisUtterance(cleanText);
    
    const preferredVoice = getNaturalVoice();
    if (preferredVoice) utterance.voice = preferredVoice;

    utterance.pitch = 1.0; 
    utterance.rate = 1.05;

    utterance.onend = () => {
        isSpeaking = false;
        
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
        speak("Connection glitch. Say that again?", false);
    }
}

recognition.onresult = (event) => {
    // INSTANT INTERRUPTION: If Ultron is talking and you speak, cut his audio immediately!
    if (isSpeaking) {
        synth.cancel();
        isSpeaking = false;
    }

    let finalTranscript = "";
    let interimTranscript = "";

    for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcriptChunk = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
            finalTranscript += transcriptChunk;
        } else {
            interimTranscript += transcriptChunk;
        }
    }

    let currentText = (finalTranscript || interimTranscript).trim();
    if (!currentText) return;

    transcriptDisplay.innerText = `"${currentText}"`;

    const lowerText = currentText.toLowerCase();

    // 1. Activation
    if (!isAwake) {
        if (lowerText.includes(WAKE_WORD)) {
            isAwake = true;
            speak("Online. What do you need?");
        }
        return;
    }

    // 2. Shutdown
    const isShutdownReq = SHUTDOWN_COMMANDS.some(cmd => lowerText.includes(cmd));
    if (isAwake && isShutdownReq && !isProcessing) {
        isProcessing = true;
        clearTimeout(speechSilenceTimer);
        speak("Going into standby.", true);
        return;
    }

    // 3. Silence Buffer for full sentence capture without duplication
    if (isAwake && !isProcessing && finalTranscript.length > 0) {
        clearTimeout(speechSilenceTimer);
        speechSilenceTimer = setTimeout(() => {
            let cleanMsg = finalTranscript.replace(new RegExp(WAKE_WORD, "gi"), "").trim();
            if (cleanMsg.length > 0) {
                sendToBackend(cleanMsg);
            }
        }, 1200); // 1.2 second pause triggers send
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
    
