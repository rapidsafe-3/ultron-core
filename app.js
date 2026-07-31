const BACKEND_URL = "/chat";
const WAKE_WORD = "ultron";
const SHUTDOWN_COMMANDS = ["shut down", "go to sleep", "sleep", "turn off", "power down"];

const core = document.getElementById('ultron-core');
const statusText = document.getElementById('status-text');
const transcriptDisplay = document.getElementById('transcript-display');
const initBtn = document.getElementById('init-btn');

let isAwake = false;
let isProcessing = false;
let isSpeaking = false;

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

// Select natural human voice
function getNaturalVoice() {
    const voices = synth.getVoices();
    // Prioritize natural high-quality human voices available in Android/Chrome
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

    utterance.pitch = 1.0; // Natural pitch
    utterance.rate = 1.0;  // Natural speech pace

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

recognition.onresult = async (event) => {
    // Avoid listening to own voice output
    if (isSpeaking) return;

    let transcript = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript.toLowerCase();
    }

    transcriptDisplay.innerText = `"${transcript}"`;

    // 1. Activation
    if (!isAwake) {
        if (transcript.includes(WAKE_WORD)) {
            isAwake = true;
            speak("Online and ready. How can I assist you?");
        }
        return;
    }

    // 2. Shutdown
    const isShutdownReq = SHUTDOWN_COMMANDS.some(cmd => transcript.includes(cmd));
    if (isAwake && isShutdownReq && !isProcessing) {
        isProcessing = true;
        speak("Entering standby mode.", true);
        return;
    }

    // 3. Continuous Conversation
    if (isAwake && !isProcessing && event.results[event.results.length - 1].isFinal) {
        const cleanCommand = transcript.replace(WAKE_WORD, "").trim();
        if (!cleanCommand) return;

        isProcessing = true;
        setCoreState('core-processing', 'THINKING');

        try {
            const response = await fetch(BACKEND_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: cleanCommand })
            });

            if (!response.ok) throw new Error("Backend error");

            const data = await response.json();
            speak(data.response, false);

        } catch (error) {
            console.error(error);
            speak("I am unable to connect to core services right now.", false);
        }
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

// Ensure voices are loaded
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
