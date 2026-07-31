const BACKEND_URL = "http://127.0.0.1:8000/chat"; 
const WAKE_WORD = "ultron";
const SHUTDOWN_COMMANDS = ["shut down", "ultron shut down", "go to sleep", "sleep", "turn off"];

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
    statusText.innerText = "MIC NOT SUPPORTED";
    transcriptDisplay.innerText = "Use Google Chrome on Android directly.";
}

const recognition = new SpeechRecognition();
recognition.continuous = true;
recognition.interimResults = true;
recognition.lang = 'en-US';

function setCoreState(stateClass, text) {
    core.className = stateClass;
    statusText.innerText = text;
}

// Function to speak text without shutting down the session
function speak(text, shouldShutdown = false) {
    isSpeaking = true;
    setCoreState('core-speaking', 'ULTRON RESPONDING');
    
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.pitch = 0.8; // Deep, commanding tone
    utterance.rate = 1.0;

    utterance.onend = () => {
        isSpeaking = false;
        
        if (shouldShutdown) {
            isAwake = false;
            isProcessing = false;
            setCoreState('core-idle', 'SYSTEM OFFLINE');
            transcriptDisplay.innerText = `Say "${WAKE_WORD.toUpperCase()}" to wake me up.`;
        } else {
            // STAY AWAKE and immediately start listening for your next command!
            isProcessing = false;
            setCoreState('core-listening', 'ACTIVE & LISTENING...');
            transcriptDisplay.innerText = "I am listening...";
        }
    };

    synth.speak(utterance);
}

recognition.onresult = async (event) => {
    // Ignore input if Ultron is currently talking to avoid hearing himself
    if (isSpeaking) return;

    let transcript = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript.toLowerCase();
    }

    transcriptDisplay.innerText = `"${transcript}"`;

    // 1. WAKE UP LOGIC (If currently asleep)
    if (!isAwake) {
        if (transcript.includes(WAKE_WORD)) {
            isAwake = true;
            speak("I am online. What do you require?");
        }
        return;
    }

    // 2. SHUTDOWN LOGIC (If awake and you command him to sleep)
    const isShutdownReq = SHUTDOWN_COMMANDS.some(cmd => transcript.includes(cmd));
    if (isAwake && isShutdownReq && !isProcessing) {
        isProcessing = true;
        speak("Deactivating systems. Goodbye.", true); // True triggers sleep
        return;
    }

    // 3. CONTINUOUS CONVERSATION LOGIC (If awake and you ask anything)
    if (isAwake && !isProcessing && event.results[event.results.length - 1].isFinal) {
        // Strip the wake word if you happen to say it again
        const cleanCommand = transcript.replace(WAKE_WORD, "").trim();
        if (!cleanCommand) return;

        isProcessing = true;
        setCoreState('core-processing', 'PROCESSING...');

        try {
            const response = await fetch(BACKEND_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: cleanCommand })
            });

            if (!response.ok) throw new Error("Backend offline");

            const data = await response.json();
            speak(data.response, false); // Keep awake after speaking!

        } catch (error) {
            console.error(error);
            speak("Core server unreachable.", false);
        }
    }
};

recognition.onerror = (e) => {
    console.log("Speech Error: ", e.error);
    if (e.error === 'not-allowed') {
        statusText.innerText = "MIC PERMISSION DENIED";
    }
};

recognition.onend = () => {
    // Force recognition to stay running continuously in background
    try { recognition.start(); } catch (e) {}
};

initBtn.addEventListener('click', () => {
    try {
        recognition.start();
        initBtn.style.display = 'none';
        setCoreState('core-idle', 'AWAITING WAKE WORD');
        transcriptDisplay.innerText = `Say "${WAKE_WORD.toUpperCase()}" to activate`;
    } catch (err) {
        alert("Microphone error. Tap debug view or open directly in Chrome!");
    }
});
