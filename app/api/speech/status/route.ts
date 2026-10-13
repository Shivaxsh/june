import { localRequest, speechStatus } from '@/lib/server/speech';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export async function GET(request: Request) {
  if (!localRequest(request)) return Response.json({ error: { code: 'origin', message: 'Open June’s local page to check speech.' } }, { status: 403 });
  return Response.json(await speechStatus(), { headers: { 'Cache-Control': 'no-store' } });
}
