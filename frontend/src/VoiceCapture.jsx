import { useEffect, useRef, useState } from "react";
import { Mic, MicOff } from "lucide-react";
import { transcribeAudio } from "./services/api.js";

function resampleToPcm16(input, sourceRate, targetRate = 16_000) {
  const ratio = sourceRate / targetRate;
  const output = new Int16Array(Math.floor(input.length / ratio));
  for (let index = 0; index < output.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, input[Math.floor(index * ratio)]));
    output[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return output;
}

export default function VoiceCapture({
  disabled,
  onTranscript,
  onError,
  onState,
  onLevel,
  className = "",
  children,
  buttonRef,
  ariaLabel = "Start microphone",
  stopLabel = "Stop listening",
}) {
  const [listening, setListening] = useState(false);
  const [processing, setProcessing] = useState(false);
  const capture = useRef(null);

  const stop = async () => {
    const current = capture.current;
    if (!current) return;
    capture.current = null;
    current.processor.disconnect();
    current.source.disconnect();
    current.stream.getTracks().forEach((track) => track.stop());
    await current.context.close();
    setListening(false);
    onState?.(false);
    onLevel?.(0);
    setProcessing(true);
    try {
      const length = current.chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      if (!length) throw new Error("I didn't hear anything. Try again when you're ready.");
      const merged = new Float32Array(length);
      let offset = 0;
      current.chunks.forEach((chunk) => {
        merged.set(chunk, offset);
        offset += chunk.length;
      });
      const pcm = resampleToPcm16(merged, current.sampleRate);
      const result = await transcribeAudio(pcm, 16_000);
      if (!result.text.trim()) throw new Error("I couldn't make out those words. Please try again.");
      onTranscript(result.text);
    } catch (error) {
      onError(error.message);
    } finally {
      setProcessing(false);
    }
  };

  const start = async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      onError("This browser can't access a microphone.");
      return;
    }
    let stream;
    let context;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      context = new AudioContext();
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const chunks = [];
      let sampleCount = 0;
      processor.onaudioprocess = (event) => {
        const chunk = new Float32Array(event.inputBuffer.getChannelData(0));
        chunks.push(chunk);
        sampleCount += chunk.length;
        const sumSquares = chunk.reduce((sum, sample) => sum + sample * sample, 0);
        onLevel?.(Math.min(1, Math.sqrt(sumSquares / chunk.length) * 5));
        event.outputBuffer.getChannelData(0).fill(0);
        if (sampleCount > context.sampleRate * 60) {
          void stop();
        }
      };
      source.connect(processor);
      processor.connect(context.destination);
      capture.current = { stream, context, source, processor, chunks, sampleRate: context.sampleRate };
      setListening(true);
      onState?.(true);
    } catch (error) {
      stream?.getTracks().forEach((track) => track.stop());
      if (context && context.state !== "closed") void context.close();
      onError(error.name === "NotAllowedError"
        ? "Microphone access was denied. Allow it in your browser when you want to use voice."
        : "I couldn't start the microphone. Check that it is connected and available.");
    }
  };

  const toggle = () => {
    if (listening) void stop();
    else void start();
  };

  useEffect(() => () => {
    const current = capture.current;
    if (!current) return;
    current.processor.disconnect();
    current.source.disconnect();
    current.stream.getTracks().forEach((track) => track.stop());
    void current.context.close();
    onLevel?.(0);
  }, []);

  return (
    <button
      ref={buttonRef}
      className={`voice-button ${listening ? "voice-listening" : ""} ${className}`}
      type="button"
      disabled={disabled || processing}
      onClick={toggle}
      aria-pressed={listening}
      aria-label={listening ? stopLabel : ariaLabel}
      title={listening ? "Click to stop and transcribe" : "Click to start microphone"}
    >
      {children || (listening ? <MicOff size={17} /> : <Mic size={17} />)}
    </button>
  );
}
