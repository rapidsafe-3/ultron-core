const coreContainer = document.getElementById('core-container');
const statusText = document.getElementById('status-text');
const transcriptText = document.getElementById('transcript-text');

let ws;
let currentAudio = null;
let mediaRecorder = null;
let audioChunks = [];
let audioContext = null;
let analyser = null;

let isRecording = false;
let isProcessing = false;
let silenceStart = null;

const SILENCE_THRESHOLD = -45; // dB volume threshold for voice detection
const SILENCE_DURATION = 1200; // 1.2s silence triggers auto-send

const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${wsProtocol}//${window.location.host}/ws`;

function connectWebSocket() {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        statusText.innerText = "SYSTEM ONLINE";
        coreContainer.className = "jarvis-container state-idle";
        initAudioEngine();
    };

    ws.onmessage = async (event) => {
        if (typeof event.data === "string") {
            const data = JSON.parse(event.data);
            if (data.type === "transcript") {
                transcriptText.innerText = `You: "${data.text}"`;
            } else if (data.type === "response_text") {
                transcriptText.innerText = `Ultron: "${data.text}"`;
            }
        } else {
            // Neural Voice Playback
            coreContainer.className = "jarvis-container state-speaking";
            statusText.innerText = "RESPONDING";

            const audioBlob = new Blob([event.data], { type: 'audio/mp3' });
            const audioUrl = URL.createObjectURL(audioBlob);

            if (currentAudio) currentAudio.pause();

            currentAudio = new Audio(audioUrl);
            currentAudio.onended = () => {
                coreContainer.className = "jarvis-container state-idle";
                statusText.innerText = "LISTENING...";
                isProcessing = false;
            };
            await currentAudio.play();
        }
    };

    ws.onclose = () => {
        statusText.innerText = "RECONNECTING...";
        setTimeout(connectWebSocket, 3000);
    };
}

async function initAudioEngine() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const source = audioContext.createMediaStreamSource(stream);
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 512;
        source.connect(analyser);

        mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.ondataavailable = e => audioChunks.push(e.data);

        mediaRecorder.onstop = () => {
            if (audioChunks.length > 0 && ws && ws.readyState === WebSocket.OPEN) {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                ws.send(audioBlob); // Stream raw audio to Whisper V3
                
                isProcessing = true;
                coreContainer.className = "jarvis-container state-processing";
                statusText.innerText = "THINKING...";
            }
            audioChunks = [];
        };

        monitorVolume();

    } catch (err) {
        console.error("Mic Access Error:", err);
        statusText.innerText = "MIC PERMISSION REQUIRED";
    }
}

// Continuous Decibel Level Voice Activity Detection (VAD)
function monitorVolume() {
    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    
    function checkAudioLevel() {
        if (isProcessing) {
            requestAnimationFrame(checkAudioLevel);
            return;
        }

        analyser.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
            sum += dataArray[i];
        }
        let average = sum / dataArray.length;
        let dB = 20 * Math.log10(average / 255);

        // Speech Detected
        if (dB > SILENCE_THRESHOLD) {
            silenceStart = null;
            if (!isRecording) {
                isRecording = true;
                audioChunks = [];
                mediaRecorder.start();
                coreContainer.className = "jarvis-container state-listening";
                statusText.innerText = "LISTENING...";
            }
        } else if (isRecording) {
            // Silence Detected
            if (!silenceStart) {
                silenceStart = Date.now();
            } else if (Date.now() - silenceStart > SILENCE_DURATION) {
                isRecording = false;
                silenceStart = null;
                mediaRecorder.stop(); // Stops and sends recording to server
            }
        }

        requestAnimationFrame(checkAudioLevel);
    }

    checkAudioLevel();
}

connectWebSocket();
