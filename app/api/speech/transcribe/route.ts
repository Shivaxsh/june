import { localRequest, readAudio, transcribe, SpeechError } from '@/lib/server/speech';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export async function POST(request: Request) {
  if (!localRequest(request)) return Response.json({ error: { code: 'origin', message: 'Use June’s local page to transcribe speech.' } }, { status: 403 });
  if (request.headers.get('content-type')?.split(';')[0].trim() !== 'audio/wav') return Response.json({ error: { code: 'format', message: 'Send a WAV recording from June’s listening controls.' } }, { status: 415 });
  try {
    const result = await transcribe(await readAudio(request), request.signal);
    return Response.json(result, { headers: { 'Cache-Control': 'no-store' } });
  } catch (error) {
    const failure = error instanceof SpeechError ? error : request.signal.aborted
      ? new SpeechError('cancelled', 'Transcription cancelled.', 499)
      : new SpeechError('transcription-failed', 'June could not transcribe this recording. Refresh speech and try again.');
    return Response.json({ error: { code: failure.code, message: failure.message } }, { status: failure.status, headers: { 'Cache-Control': 'no-store' } });
  }
}
