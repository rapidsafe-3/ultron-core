const coreContainer = document.getElementById('core-container');
const statusText = document.getElementById('status-text');
const transcriptText = document.getElementById('transcript-text');
const initBtn = document.getElementById('init-btn');
const terminal = document.getElementById('terminal-panel');

let ws;
let currentAudio = null;
let mediaRecorder = null;
let audioChunks = [];
let audioContext = null;
let analyser = null;

let isRecording = false;
let isProcessing = false;
let isAwake = false; // System starts asleep
let silenceStart = null;

// Audio Tuning Parameters
const SILENCE_THRESHOLD = -45; // dB volume threshold for speaking
const SILENCE_DURATION = 1500; // 1.5s of silence triggers sending

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
            
            if (data.type === "shutdown_command") {
                isAwake = false;
                return;
            }
            
            if (data.type === "transcript") {
                
                let heard = data.text.toLowerCase();
                
                // WAKE WORD LOGIC
                if (!isAwake) {
                    if (heard.includes("ultron")) {
                        isAwake = true;
                        statusText.innerText = "ONLINE & LISTENING";
                        transcriptText.innerText = "Awaiting command...";
                        coreContainer.className = "jarvis-container state-listening";
                    }
                    isProcessing = false;
                    return; // Don't process the wake word as a chat command
                }
                
                transcriptText.innerText = `You: "${data.text}"`;

            } else if (data.type === "response_text") {
                transcriptText.innerText = `Ultron: "${data.text}"`;
            }
        } else {
            // Audio Playback
            coreContainer.className = "jarvis-container state-speaking";
            statusText.innerText = "RESPONDING";

            const audioBlob = new Blob([event.data], { type: 'audio/mp3' });
            const audioUrl = URL.createObjectURL(audioBlob);

            if (currentAudio) currentAudio.pause();

            currentAudio = new Audio(audioUrl);
            currentAudio.onended = () => {
                if(isAwake) {
                    coreContainer.className = "jarvis-container state-listening";
                    statusText.innerText = "LISTENING...";
                } else {
                    coreContainer.className = "jarvis-container state-idle";
                    statusText.innerText = "STANDBY (Say 'Ultron')";
                }
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
                ws.send(audioBlob); 
                
                isProcessing = true;
                if(isAwake) {
                    coreContainer.className = "jarvis-container state-processing";
                    statusText.innerText = "PROCESSING...";
                }
            }
            audioChunks = [];
        };

        monitorVolume();

    } catch (err) {
        console.error("Mic Error:", err);
        alert("Allow Microphone to use Ultron.");
    }
}

// Custom VAD (Voice Activity Detection)
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

        // Someone is talking
        if (dB > SILENCE_THRESHOLD) {
            silenceStart = null;
            if (!isRecording) {
                isRecording = true;
                audioChunks = [];
                mediaRecorder.start();
                if(isAwake) {
                    coreContainer.className = "jarvis-container state-listening";
                    statusText.innerText = "HEARING...";
                }
            }
        } else if (isRecording) {
            // Silence started
            if (!silenceStart) {
                silenceStart = Date.now();
            } else if (Date.now() - silenceStart > SILENCE_DURATION) {
                // Stopped talking for 1.5 seconds -> Send it!
                isRecording = false;
                silenceStart = null;
                mediaRecorder.stop(); 
            }
        }

        requestAnimationFrame(checkAudioLevel);
    }

    checkAudioLevel();
}

// Ensure audio context unlocks on mobile
initBtn.addEventListener('click', () => {
    initBtn.style.display = 'none';
    terminal.style.display = 'block';
    statusText.innerText = "STANDBY (Say 'Ultron')";
    transcriptText.innerText = "System activated.";
    initAudioEngine();
});

connectWebSocket();
                        
