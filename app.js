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

// TUNED FOR WHISPERS 
const SILENCE_THRESHOLD = -55; 
const SILENCE_DURATION = 1200; 

const WS_URL = `wss://${window.location.host}/ws`;

function connectWebSocket() {
    ws = new WebSocket(WS_URL);
    
    // Tell the WebSocket we expect ArrayBuffer (binary) data
    ws.binaryType = "arraybuffer"; 
    
    ws.onmessage = async (event) => {
        if (typeof event.data === "string") {
            const data = JSON.parse(event.data);
            if (data.type === "status") {
                isAwake = (data.state === "awake");
                coreContainer.className = isAwake ? "proton-container state-idle" : "proton-container state-sleep";
            }
        } 
        else if (event.data instanceof ArrayBuffer) {
            coreContainer.className = "proton-container state-speaking";
            
            // The complete audio file is here, ready to play!
            const audioBlob = new Blob([event.data], { type: 'audio/mp3' });
            const audioUrl = URL.createObjectURL(audioBlob);
            
            if (currentAudio) currentAudio.pause();
            currentAudio = new Audio(audioUrl);
            
            currentAudio.onended = () => {
                coreContainer.className = isAwake ? "proton-container state-idle" : "proton-container state-sleep";
                isProcessing = false;
            };
            currentAudio.play();
        }
    };
    ws.onclose = () => setTimeout(connectWebSocket, 3000);
}

async function initAudioEngine() {
    try {
        // Force the browser to use standard media routing instead of communication routing
        const constraints = {
            audio: {
                echoCancellation: false,
                noiseSuppression: false,
                autoGainControl: false,
                channelCount: 1 
            }
        };
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        
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

        if (dB > SILENCE_THRESHOLD) {
            silenceStart = null;
            
            // INSTANT INTERRUPT
            if (currentAudio && !currentAudio.paused) {
                currentAudio.pause();
                isProcessing = false;
                coreContainer.className = isAwake ? "proton-container state-idle" : "proton-container state-sleep";
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
    coreContainer.className = "proton-container state-sleep"; // Starts asleep
    initAudioEngine();
});

connectWebSocket();
