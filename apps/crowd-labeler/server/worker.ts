import catalog from '../src/data/review-maps.json';
import { initialState, questions, modes, familiarityOptions } from '../src/lib/survey';
import type { CatalogMap, Profile, Submission } from '../src/lib/survey';
import { ownerApi } from './owner';

type Row = Record<string, string | number>;
type Statement = { bind(...values: unknown[]): Statement; first<T = Row>(): Promise<T | null>; all<T = Row>(): Promise<{ results: T[] }>; run(): Promise<unknown> };
export type Env = { OWNER_EMAIL?: string; OWNER_USER_ID?: string; DB: { prepare(sql: string): Statement }; ASSETS: { fetch(request: Request): Promise<Response> } };
const maps = new Map((catalog as CatalogMap[]).map(m => [m.id, m]));

const json = (data: unknown, status = 200, headers: Record<string, string> = {}) => Response.json(data, { status, headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', ...headers } });
class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }
function need(condition: unknown, message = 'Invalid review'): asserts condition { if (!condition) throw new ApiError(400, message); }
const str = (x: unknown, max: number) => typeof x === 'string' && x.length <= max;
const uuid = (x: unknown) => typeof x === 'string' && /^[a-f0-9-]{36}$/i.test(x);
async function digest(s: string) { return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)))).map(x => x.toString(16).padStart(2, '0')).join(''); }
function profile(value: unknown): Profile {
  const p = value as Profile;
  need(p && str(p.name, 80) && str(p.rating, 8) && /^(|-?\d{1,5})$/.test(p.rating), 'Invalid player profile');
  need(['Global','1v1','2v2','3v3','4v4'].includes(p.ratingMode));
  need(['Less than 6 months','6–12 months','1–3 years','3–5 years','5+ years'].includes(p.experience));
  need(Array.isArray(p.modes) && p.modes.length > 0 && p.modes.length <= modes.length && p.modes.every(m => modes.includes(m)));
  need(p.language === undefined || ['en','ru'].includes(p.language));
  return { name: p.name.trim(), rating: p.rating, ratingMode: p.ratingMode, experience: p.experience, modes: [...new Set(p.modes)], language: p.language || 'en', saved: true };
}
async function body(request: Request) {
  need(request.headers.get('content-type')?.startsWith('application/json'), 'JSON required');
  if (Number(request.headers.get('content-length')) > 20000) throw new ApiError(413, 'Request too large');
  const reader = request.body?.getReader(); need(reader, 'Missing request body');
  const chunks: Uint8Array[] = []; let size = 0;
  while (true) { const part = await reader.read(); if (part.done) break; size += part.value.length; if (size > 20000) { await reader.cancel(); throw new ApiError(413, 'Request too large'); } chunks.push(part.value); }
  const data = new Uint8Array(size); let offset = 0; for (const c of chunks) { data.set(c, offset); offset += c.length; }
  try { return JSON.parse(new TextDecoder().decode(data)); } catch { throw new ApiError(400, 'Invalid JSON'); }
}
async function participant(request: Request, env: Env) {
  const token = request.headers.get('Cookie')?.match(/(?:^|;\s*)mapgen_session=([a-f0-9-]{73})(?:;|$)/)?.[1];
  if (!token) return null;
  return env.DB.prepare('SELECT id, profile FROM participants WHERE token_hash = ?').bind(await digest(token)).first<{ id: string; profile: string }>();
}
async function rateLimit(env: Env, key: string, limit: number, seconds: number) {
  const bucket = Math.floor(Date.now() / (seconds * 1000));
  const row = await env.DB.prepare('INSERT INTO request_limits (key, count, expires_at) VALUES (?, 1, ?) ON CONFLICT(key) DO UPDATE SET count = count + 1 RETURNING count').bind(`${key}:${bucket}`, (bucket + 1) * seconds).first<{ count: number }>();
  if (row && row.count > limit) throw new ApiError(429, 'Too many requests. Please try again later.');
}
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/owner' || url.pathname === '/owner/') {
      const page = await env.ASSETS.fetch(new Request(new URL('/', url), request));
      const headers = new Headers(page.headers);
      headers.set('Cache-Control', 'private, no-store');
      headers.set('X-Robots-Tag', 'noindex, nofollow');
      return new Response(page.body, { status: page.status, headers });
    }
    if (!url.pathname.startsWith('/api/')) return env.ASSETS.fetch(request);
    try {
      const settings = { ...initialState(catalog as CatalogMap[]).settings, revision: 'public-v1' };
      const emptyProfile = initialState([]).profile;
      const origin = request.headers.get('Origin');
      if (origin && origin !== url.origin) throw new ApiError(403, 'Cross-origin request rejected');
      if (request.headers.get('Sec-Fetch-Site') === 'cross-site') throw new ApiError(403, 'Cross-site request rejected');
      if (url.pathname.startsWith('/api/owner/')) return await ownerApi(request, env, catalog as CatalogMap[]);
      if (url.pathname === '/api/health' && request.method === 'GET') {
        await env.DB.prepare('SELECT id FROM participants LIMIT 1').first();
        return json({ ok: true, schemaVersion: 3 });
      }
      let person = await participant(request, env);
      if (url.pathname === '/api/session' && request.method === 'GET') {
        let headers = {};
        if (!person) {
          // Only a short-lived hash bucket is retained, never the raw IP address.
          await rateLimit(env, `session:${await digest(request.headers.get('CF-Connecting-IP') || 'local')}`, 30, 3600);
          await env.DB.prepare('DELETE FROM request_limits WHERE expires_at < ?').bind(Math.floor(Date.now() / 1000)).run();
          const token = `${crypto.randomUUID()}-${crypto.randomUUID()}`;
          person = { id: crypto.randomUUID(), profile: JSON.stringify(emptyProfile) };
          await env.DB.prepare('INSERT INTO participants (id, token_hash, profile, created_at) VALUES (?, ?, ?, ?)').bind(person.id, await digest(token), person.profile, new Date().toISOString()).run();
          headers = { 'Set-Cookie': `mapgen_session=${token}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=31536000` };
        }
        const rows = await env.DB.prepare('SELECT payload FROM reviews WHERE participant_id = ? ORDER BY received_at').bind(person.id).all<{ payload: string }>();
        return json({ respondentId: person.id, profile: JSON.parse(person.profile), submissions: rows.results.map(r => JSON.parse(r.payload)), settings }, 200, headers);
      }
      if (!person) throw new ApiError(401, 'Please reload to restore your session.');
      if (url.pathname === '/api/profile' && request.method === 'PUT') {
        await rateLimit(env, `profile:${person.id}`, 60, 60);
        const p = profile(await body(request));
        await env.DB.prepare('UPDATE participants SET profile = ? WHERE id = ?').bind(JSON.stringify(p), person.id).run();
        return json(p);
      }
      if (url.pathname === '/api/reviews' && request.method === 'POST') {
        await rateLimit(env, `review:${person.id}`, 30, 60);
        const s = await body(request) as Submission;
        need(s && uuid(s.id));
        const existing = await env.DB.prepare('SELECT participant_id, payload FROM reviews WHERE id = ?').bind(s.id).first<{ participant_id: string; payload: string }>();
        if (existing) { if (existing.participant_id !== person.id) throw new ApiError(409, 'Review ID already used'); return json(JSON.parse(existing.payload)); }
        const map = maps.get(s.mapId); need(map && s.mapVersion === map.version, 'Unknown map version');
        need(s.scaleVersion === 5 && s.calibrationRevision === settings.revision, 'Please reload for the current questionnaire');
        need(s.answers && Object.keys(s.answers).length === questions.length && questions.every(q => s.answers[q.id] === 'unknown' || Number.isInteger(s.answers[q.id]) && Number(s.answers[q.id]) >= 1 && Number(s.answers[q.id]) <= 5));
        need(familiarityOptions.includes(s.familiarity) && str(s.configuration, 100) && s.configuration.trim().length > 0);
        need(str(s.setup, 1200) && str(s.note, 1200) && str(s.uniqueText ?? '', 1200));
        need(Array.isArray(s.biomes) && s.biomes.length <= 10 && s.biomes.every(x => ['Earthlike','Martian','Lunar','Desert','Tundra','Forest','Volcanic','Tropical','Barren rock','Snow & ice'].includes(x)));
        need(Array.isArray(s.uniqueTraits) && s.uniqueTraits.length <= 12 && s.uniqueTraits.every(x => str(x, 100)));
        need(Number.isFinite(s.secondsSpent) && s.secondsSpent >= 0 && s.secondsSpent <= 31536000 && typeof s.suggestionsShown === 'boolean');
        need(s.phase === 'calibration' || s.phase === 'collection');
        if (s.phase === 'calibration') need(settings.anchors.some(a => a.mapId === s.mapId));
        else {
          const completed = await env.DB.prepare("SELECT DISTINCT map_id FROM reviews WHERE participant_id = ? AND phase = 'calibration'").bind(person.id).all<{ map_id: string }>();
          need(settings.anchors.every(a => completed.results.some(r => r.map_id === a.mapId)), 'Complete calibration first');
        }
        const p = profile(s.profile); need(JSON.parse(person.profile).saved, 'Save your player profile first');
        const saved: Submission = { id: s.id, respondentId: person.id, mapId: map.id, mapVersion: map.version, scaleVersion: 5, profile: p, familiarity: s.familiarity, configuration: s.configuration.trim(), setup: s.setup, answers: s.answers, note: s.note, biomes: s.biomes, uniqueTraits: s.uniqueTraits, uniqueText: s.uniqueText || '', phase: s.phase, createdAt: new Date().toISOString(), secondsSpent: Math.round(s.secondsSpent), suggestionsShown: s.suggestionsShown, calibrationRevision: settings.revision };
        await env.DB.prepare('INSERT INTO reviews (id, participant_id, map_id, phase, payload, received_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING').bind(saved.id, person.id, saved.mapId, saved.phase, JSON.stringify(saved), saved.createdAt).run();
        const result = await env.DB.prepare('SELECT participant_id, payload FROM reviews WHERE id = ?').bind(saved.id).first<{ participant_id: string; payload: string }>();
        if (result?.participant_id !== person.id) throw new ApiError(409, 'Review ID already used');
        return json(JSON.parse(result.payload), 201);
      }
      return json({ error: 'Not found' }, 404);
    } catch (error) {
      if (error instanceof ApiError) return json({ error: error.message }, error.status);
      console.error('MapGen storage operation failed', error instanceof Error ? error.message : 'Unknown error');
      return json({ error: 'Storage is temporarily unavailable. Your answers are still on screen; please retry.' }, 503);
    }
  },
};
