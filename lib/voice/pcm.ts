// Both browser and server share the strict 16 kHz mono PCM WAV contract.
export const MAX_AUDIO_BYTES = 1048576;
export const MAX_RECORD_SECONDS = 30;
export function encodeWav(samples: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + samples.length * 2); const view = new DataView(buffer);
  const text = (offset: number, value: string) => { for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i)); };
  text(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true); text(8, 'WAVE');
  text(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, 'data'); view.setUint32(40, samples.length * 2, true);
  samples.forEach((sample, i) => { const x = Math.max(-1, Math.min(1, Number.isFinite(sample) ? sample : 0)); view.setInt16(44 + i * 2, Math.round(x * (x < 0 ? 32768 : 32767)), true); });
  return buffer;
}
export function validateWav(data: Uint8Array): { durationMs: number; rms: number } {
  if (data.byteLength > MAX_AUDIO_BYTES) throw new Error('Audio is too large. Record at most 30 seconds.');
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const text = (a: number, b: number) => new TextDecoder().decode(data.subarray(a, b));
  if (data.byteLength < 44 || text(0, 4) !== 'RIFF' || text(8, 12) !== 'WAVE' || text(12, 16) !== 'fmt ' || text(36, 40) !== 'data') throw new Error('Invalid WAV audio. Try recording again.');
  if (view.getUint32(4, true) !== data.byteLength - 8 || view.getUint32(40, true) !== data.byteLength - 44 || (data.byteLength - 44) % 2 !== 0) throw new Error('WAV size does not match its data.');
  if (view.getUint32(16, true) !== 16 || view.getUint16(20, true) !== 1 || view.getUint16(22, true) !== 1 || view.getUint32(24, true) !== 16000 || view.getUint32(28, true) !== 32000 || view.getUint16(32, true) !== 2 || view.getUint16(34, true) !== 16) throw new Error('Use mono 16 kHz 16-bit PCM WAV format.');
  const durationMs = (data.byteLength - 44) / 32;
  if (durationMs < 500) throw new Error('Recording is too short. Hold to talk for at least half a second.');
  if (durationMs > MAX_RECORD_SECONDS * 1000) throw new Error('Audio is too large. Record at most 30 seconds.');
  let sum = 0; for (let i = 44; i < data.byteLength; i += 2) sum += (view.getInt16(i, true) / 32768) ** 2;
  const rms = Math.sqrt(sum / ((data.byteLength - 44) / 2));
  if (rms < 0.001) throw new Error('Recording is too quiet to recognise speech. Check the microphone and try again.');
  return { durationMs, rms };
}
