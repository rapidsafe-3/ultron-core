const core = document.getElementById('ultron-core');
const statusText = document.getElementById('status-text');
const transcriptDisplay = document.getElementById('transcript-display');
const initBtn = document.getElementById('init-btn');

let mediaRecorder = null;
let audioChunks = [];
let currentAudioPlayer = null;
let isRecording = false;
let isProcessing = false;

function setCoreState(stateClass, text) {
    core.className = stateClass;
    statusText.innerText = text;
}

// Play incoming Neural MP3 audio stream from server
async function playNeuralSpeech(text) {
    setCoreState('core-speaking', 'ULTRON');
    
    try {
        const response = await fetch('/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text })
        });

        if (!response.ok) throw new Error("TTS Generation Failed");

        const audioBlob = await response.blob();
        const audioUrl = URL.createObjectURL(audioBlob);

        if (currentAudioPlayer) {
            currentAudioPlayer.pause();
        }

        currentAudioPlayer = new Audio(audioUrl);
        
        currentAudioPlayer.onended = () => {
            setCoreState('core-idle', 'READY');
            transcriptDisplay.innerText = "Tap core or hold microphone to speak...";
            isProcessing = false;
        };

        await currentAudioPlayer.play();

    } catch (err) {
        console.error("Audio playback error:", err);
        setCoreState('core-idle', 'READY');
        isProcessing = false;
    }
}

// Send audio blob to Groq Whisper for instant transcription
async function processRecordedAudio(blob) {
    if (isProcessing) return;
    isProcessing = true;

    setCoreState('core-processing', 'TRANSCRIBING...');
    transcriptDisplay.innerText = "Processing audio...";

    const formData = new FormData();
    formData.append('file', blob, 'recording.webm');

    try {
        // 1. Transcribe audio with Groq Whisper V3
        const sttResponse = await fetch('/transcribe', {
            method: 'POST',
            body: formData
        });

        if (!sttResponse.ok) throw new Error("STT failed");

        const sttData = await sttResponse.json();
        const userText = sttData.text;

        if (!userText || userText.length < 2) {
            setCoreState('core-idle', 'READY');
            transcriptDisplay.innerText = "Didn't hear clearly. Try again.";
            isProcessing = false;
            return;
        }

        transcriptDisplay.innerText = `"${userText}"`;
        setCoreState('core-processing', 'THINKING...');

        // 2. Query Ultron Brain
        const chatResponse = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: userText })
        });

        if (!chatResponse.ok) throw new Error("Chat failed");

        const chatData = await chatResponse.json();
        
        // 3. Play Neural Voice Response
        await playNeuralSpeech(chatData.response);

    } catch (error) {
        console.error(error);
        setCoreState('core-idle', 'READY');
        transcriptDisplay.innerText = "System error processing voice.";
        isProcessing = false;
    }
}

// Start audio recording
async function startRecording() {
    if (isProcessing || isRecording) return;

    // Interrupt Ultron if speaking
    if (currentAudioPlayer) {
        currentAudioPlayer.pause();
        currentAudioPlayer = null;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            processRecordedAudio(audioBlob);
            // Stop mic track to save battery
            stream.getTracks().forEach(track => track.stop());
        };

        mediaRecorder.start();
        isRecording = true;
        setCoreState('core-listening', 'LISTENING...');
        transcriptDisplay.innerText = "Recording voice...";

    } catch (err) {
        alert("Microphone access required!");
        console.error(err);
    }
}

// Stop audio recording
function stopRecording() {
    if (mediaRecorder && isRecording) {
        isRecording = false;
        mediaRecorder.stop();
    }
}

// UI Event Listeners
initBtn.addEventListener('click', () => {
    initBtn.style.display = 'none';
    setCoreState('core-idle', 'READY');
    transcriptDisplay.innerText = "Tap core to start/stop talking";
});

// Tap core to toggle mic recording
core.addEventListener('click', () => {
    if (initBtn.style.display !== 'none') return;

    if (!isRecording) {
        startRecording();
    } else {
        stopRecording();
    }
});
