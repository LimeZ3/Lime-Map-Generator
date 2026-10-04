import type { Env } from './worker';
import { initialState, questions } from '../src/lib/survey';
import type { CatalogMap } from '../src/lib/survey';

const json = (data: unknown, status = 200) => Response.json(data, { status, headers: { 'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff', 'Vary': 'Cookie' } });

// Sites dispatch authenticates visitors and supplies these headers; never take
// identity from participant profiles, cookies, query parameters or request bodies.
export function isOwner(request: Request, env: Env) {
  const id = request.headers.get('oai-authenticated-user-id')?.trim();
  const email = request.headers.get('oai-authenticated-user-email')?.trim().toLowerCase();
  if (!id || !email) return false;
  if (env.OWNER_USER_ID) return id === env.OWNER_USER_ID;
  return Boolean(env.OWNER_EMAIL && email === env.OWNER_EMAIL.trim().toLowerCase());
}

export async function ownerApi(request: Request, env: Env, catalog: CatalogMap[]) {
  if (!request.headers.get('oai-authenticated-user-id')) return json({ error: 'Sign in with ChatGPT to open the owner dashboard.' }, 401);
  if (!isOwner(request, env)) return json({ error: 'This dashboard is restricted to the site owner.' }, 403);
  if (request.method !== 'GET') return json({ error: 'Method not allowed' }, 405);
  const url = new URL(request.url);
  if (url.pathname === '/api/owner/snapshot') {
    const reviews = await env.DB.prepare('SELECT COUNT(*) AS count, COALESCE(MAX(rowid), 0) AS through FROM reviews').first();
    const participants = await env.DB.prepare('SELECT COUNT(*) AS count, COALESCE(MAX(rowid), 0) AS through FROM participants').first();
    return json({ schemaVersion: 3, exportedAt: new Date().toISOString(), reviews, participants, questionDefinitions: questions, settings: { ...initialState(catalog).settings, revision: 'public-v1' } });
  }
  const kind = url.pathname === '/api/owner/reviews' ? 'reviews' : url.pathname === '/api/owner/participants' ? 'participants' : null;
  if (!kind) return json({ error: 'Not found' }, 404);
  const after = Number(url.searchParams.get('after') ?? '0');
  const through = Number(url.searchParams.get('through'));
  if (!url.searchParams.has('through') || !Number.isSafeInteger(after) || !Number.isSafeInteger(through) || after < 0 || through < after) return json({ error: 'Invalid page cursor' }, 400);
  // Keyset pagination avoids skipped rows and includes every review present at
  // the snapshot watermark, even while new participants are submitting reviews.
  if (kind === 'reviews') {
    const result = await env.DB.prepare('SELECT rowid AS cursor, payload, received_at FROM reviews WHERE rowid > ? AND rowid <= ? ORDER BY rowid LIMIT 250').bind(after, through).all<{ cursor: number; payload: string; received_at: string }>();
    const maps = new Map(catalog.map(m => [m.id, m]));
    return json({ rows: result.results.map(r => { const s = JSON.parse(r.payload); const map = maps.get(s.mapId); return { ...s, receivedAt: r.received_at, mapName: map?.canonicalName || s.mapId, mapFolder: map?.mapDir || '' }; }), next: result.results.length === 250 ? result.results.at(-1)!.cursor : null });
  }
  // Explicit allowlist: never export session token hashes or rate-limit keys.
  const result = await env.DB.prepare('SELECT rowid AS cursor, id, profile, created_at FROM participants WHERE rowid > ? AND rowid <= ? ORDER BY rowid LIMIT 250').bind(after, through).all<{ cursor: number; id: string; profile: string; created_at: string }>();
  return json({ rows: result.results.map(r => ({ id: r.id, profile: JSON.parse(r.profile), createdAt: r.created_at })), next: result.results.length === 250 ? result.results.at(-1)!.cursor : null });
}
