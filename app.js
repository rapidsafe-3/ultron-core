const coreContainer = document.getElementById('core-container');
const overlay = document.getElementById('activation-overlay');

let ws;
let currentAudio = null;
let mediaRecorder = null;
let audioChunks = [];
let audioContext = null;
let analyser = null;

let isRecording = false;
let isProcessing = false;
let isAwake = false; 
let silenceStart = null;

// TUNED FOR WHISPERS & QUICK CUTOFF
const SILENCE_THRESHOLD = -55; 
const SILENCE_DURATION = 1200; 

const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${wsProtocol}//${window.location.host}/ws`;

function connectWebSocket() {
    ws = new WebSocket(WS_URL);
    ws.onmessage = async (event) => {
        if (typeof event.data === "string") {
            const data = JSON.parse(event.data);
            if (data.type === "sleep_command") {
                isAwake = false;
                coreContainer.className = "proton-container state-sleep";
                return;
            }
        } else {
            // Audio Playback
            coreContainer.className = "proton-container state-speaking";
            const audioBlob = new Blob([event.data], { type: 'audio/mp3' });
            const audioUrl = URL.createObjectURL(audioBlob);

            if (currentAudio) currentAudio.pause();
            currentAudio = new Audio(audioUrl);
            currentAudio.onended = () => {
                coreContainer.className = isAwake ? "proton-container state-idle" : "proton-container state-sleep";
                isProcessing = false;
            };
            await currentAudio.play();
        }
    };
    ws.onclose = () => setTimeout(connectWebSocket, 3000);
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
                ws.send(audioBlob); 
                
                if(isAwake) {
                    isProcessing = true;
                    coreContainer.className = "proton-container state-processing";
                }
            }
            audioChunks = [];
        };

        // Continuous local Wake Word detection backup
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if(SpeechRecognition) {
            const recognition = new SpeechRecognition();
            recognition.continuous = true;
            recognition.interimResults = true;
            recognition.onresult = (e) => {
                let text = "";
                for (let i = e.resultIndex; i < e.results.length; i++) {
                    text += e.results[i][0].transcript.toLowerCase();
                }
                if (!isAwake && text.includes("ultron")) {
                    isAwake = true;
                    isProcessing = false;
                    coreContainer.className = "proton-container state-listening";
                }
            };
            recognition.start();
            recognition.onend = () => recognition.start();
        }

        monitorVolume();

    } catch (err) {
        console.error("Mic Error:", err);
    }
}

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

        // INSTANT INTERRUPT & VAD
        if (dB > SILENCE_THRESHOLD) {
            silenceStart = null;
            
            // If he is talking, and you speak, shut him up instantly!
            if (currentAudio && !currentAudio.paused) {
                currentAudio.pause();
                isProcessing = false;
                coreContainer.className = "proton-container state-idle";
            }

            if (!isRecording) {
                isRecording = true;
                audioChunks = [];
                mediaRecorder.start();
                if(isAwake) coreContainer.className = "proton-container state-listening";
            }
        } else if (isRecording) {
            if (!silenceStart) {
                silenceStart = Date.now();
            } else if (Date.now() - silenceStart > SILENCE_DURATION) {
                isRecording = false;
                silenceStart = null;
                mediaRecorder.stop(); 
            }
        }

        requestAnimationFrame(checkAudioLevel);
    }
    checkAudioLevel();
}

// Single tap to start the engine, then the overlay disappears forever
overlay.addEventListener('click', () => {
    overlay.style.display = 'none';
    isAwake = true;
    coreContainer.className = "proton-container state-idle";
    initAudioEngine();
});

connectWebSocket();
                
