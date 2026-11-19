import { useEffect, useRef } from "react";
import { transcribeAudio } from "./services/api.js";

function resampleToPcm16(input, sourceRate) {
  const ratio = sourceRate / 16_000;
  const output = new Int16Array(Math.floor(input.length / ratio));
  for (let index = 0; index < output.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, input[Math.floor(index * ratio)]));
    output[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return output;
}

function joinPcm(chunks) {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const result = new Int16Array(length);
  let offset = 0;
  chunks.forEach((chunk) => {
    result.set(chunk, offset);
    offset += chunk.length;
  });
  return result;
}

export default function BackgroundWakeListener({ enabled, stream, onTranscript, onError, onState }) {
  const callbacks = useRef({ onTranscript, onError, onState });
  useEffect(() => {
    callbacks.current = { onTranscript, onError, onState };
  }, [onTranscript, onError, onState]);

  useEffect(() => {
    if (!enabled || !stream) {
      callbacks.current.onState?.(false);
      return undefined;
    }

    let active = true;
    let context;
    let source;
    let processor;
    let socket;
    let commandCapture = null;
    let wakeSamples = [];
    let transcribing = false;

    const finishCommand = async () => {
      const capture = commandCapture;
      commandCapture = null;
      if (!capture?.voiced || transcribing) return;
      transcribing = true;
      try {
        const pcm = joinPcm(capture.chunks);
        const result = await transcribeAudio(pcm, 16_000);
        if (result.text.trim()) callbacks.current.onTranscript?.(result.text);
      } catch (error) {
        callbacks.current.onError?.(error.message);
      } finally {
        transcribing = false;
      }
    };

    try {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${protocol}//${window.location.host}/api/voice/wake-word`);
      socket.binaryType = "arraybuffer";
      socket.onopen = () => {
        if (active) callbacks.current.onState?.(true);
      };
      socket.onmessage = (event) => {
        if (!active) return;
        try {
          if (JSON.parse(event.data).detected && !commandCapture) {
            commandCapture = { chunks: [], voiced: false, silence: 0, duration: 0 };
          }
        } catch {
          callbacks.current.onError?.("The local wake-word service returned an invalid response.");
        }
      };
      socket.onerror = () => {
        if (active) callbacks.current.onError?.("The local wake-word connection failed.");
      };
      socket.onclose = (event) => {
        if (!active) return;
        callbacks.current.onState?.(false);
        if (event.reason) callbacks.current.onError?.(event.reason);
      };

      context = new AudioContext();
      source = context.createMediaStreamSource(stream);
      processor = context.createScriptProcessor(4096, 1, 1);
      processor.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0);
        const pcm = resampleToPcm16(input, context.sampleRate);
        if (commandCapture) {
          const capture = commandCapture;
          capture.chunks.push(pcm);
          capture.duration += pcm.length / 16;
          let sumSquares = 0;
          for (let index = 0; index < pcm.length; index += 1) {
            const sample = pcm[index] / 32768;
            sumSquares += sample * sample;
          }
          const rms = Math.sqrt(sumSquares / Math.max(1, pcm.length));
          if (rms > 0.018) {
            capture.voiced = true;
            capture.silence = 0;
          } else if (capture.voiced) {
            capture.silence += pcm.length / 16;
          }
          if ((capture.voiced && capture.silence > 1100) || capture.duration > 9000) {
            void finishCommand();
          }
        } else if (socket.readyState === WebSocket.OPEN) {
          for (const sample of pcm) wakeSamples.push(sample);
          while (wakeSamples.length >= 1280) {
            if (socket.bufferedAmount > 128 * 1024) {
              wakeSamples = [];
              break;
            }
            const frame = Int16Array.from(wakeSamples.splice(0, 1280));
            socket.send(frame.buffer);
          }
        }
        event.outputBuffer.getChannelData(0).fill(0);
      };
      source.connect(processor);
      processor.connect(context.destination);
      void context.resume();
    } catch (error) {
      callbacks.current.onError?.(error.message);
      callbacks.current.onState?.(false);
    }

    return () => {
      active = false;
      processor?.disconnect();
      source?.disconnect();
      if (socket && socket.readyState < WebSocket.CLOSING) socket.close();
      if (context && context.state !== "closed") void context.close();
      callbacks.current.onState?.(false);
    };
  }, [enabled, stream]);

  return null;
}
