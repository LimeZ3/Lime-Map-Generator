import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, readdirSync, mkdirSync } from 'node:fs';
import { build } from 'esbuild';
mkdirSync('.tmp', { recursive: true });
await build({ entryPoints: ['server/worker.ts'], outfile: '.tmp/test-worker.mjs', bundle: true, format: 'esm', platform: 'node' });
const { default: worker } = await import('../.tmp/test-worker.mjs');
const db = new DatabaseSync(':memory:');
for (const file of readdirSync('drizzle').filter(f => f.endsWith('.sql')).sort()) db.exec(readFileSync(`drizzle/${file}`, 'utf8'));
const env = { DB: { prepare(sql) {
  let values = [];
  return { bind(...v) { values = v; return this; }, async first() { return db.prepare(sql).get(...values) ?? null; }, async all() { return { results: db.prepare(sql).all(...values) }; }, async run() { return db.prepare(sql).run(...values); } };
} }, ASSETS: { fetch: async () => new Response('static') } };
async function call(path, method = 'GET', data, cookie = '', origin = 'https://example.test') {
  return worker.fetch(new Request(`https://example.test${path}`, { method, headers: { Cookie: cookie, Origin: origin, 'Content-Type': 'application/json' }, body: data === undefined ? undefined : JSON.stringify(data) }), env);
}
const first = await call('/api/session');
assert.equal(first.status, 200);
const cookie = first.headers.get('set-cookie').split(';')[0];
assert.match(first.headers.get('set-cookie'), /HttpOnly; Secure; SameSite=Lax/);
const state = await first.json();
assert.equal(state.submissions.length, 0);
const profile = { name: 'Automated test', rating: '1800', ratingMode: 'Global', experience: 'Less than 6 months', modes: ['1v1 ladder'], saved: true, language: 'ru' };
assert.equal((await call('/api/profile', 'PUT', profile)).status, 401);
assert.equal((await call('/api/profile', 'PUT', profile, cookie, 'https://other.test')).status, 403);
assert.equal((await call('/api/profile', 'PUT', profile, cookie)).status, 200);
const catalog = JSON.parse(readFileSync('src/data/review-maps.json', 'utf8'));
const { defaultAnswers } = await import('../src/lib/survey.ts');
function review(mapId, phase = 'calibration') { return { id: crypto.randomUUID(), mapId, mapVersion: catalog.find(m => m.id === mapId).version, respondentId: 'forged', profile, scaleVersion: 5, answers: defaultAnswers(), familiarity: 'Preview', configuration: '4v4', setup: '', note: '', uniqueText: '', uniqueTraits: [], biomes: [], phase, createdAt: 'forged', secondsSpent: 10, suggestionsShown: false, calibrationRevision: 'public-v1' }; }
const submission = review(state.settings.anchors[0].mapId);
assert.equal((await call('/api/reviews', 'POST', { ...submission, answers: { ...submission.answers, quality: 6 } }, cookie)).status, 400);
assert.equal((await call('/api/reviews', 'POST', { ...submission, phase: 'collection' }, cookie)).status, 400);
const result = await call('/api/reviews', 'POST', submission, cookie);
assert.equal(result.status, 201);
assert.equal((await result.json()).respondentId, state.respondentId);
assert.equal((await call('/api/reviews', 'POST', submission, cookie)).status, 200);
assert.equal(db.prepare('SELECT COUNT(*) AS n FROM reviews').get().n, 1);
const other = await call('/api/session');
const otherCookie = other.headers.get('set-cookie').split(';')[0];
assert.equal((await other.json()).submissions.length, 0);
assert.equal((await call('/api/reviews', 'POST', submission, otherCookie)).status, 409);
for (const anchor of state.settings.anchors.slice(1)) assert.equal((await call('/api/reviews', 'POST', review(anchor.mapId), cookie)).status, 201);
assert.equal((await call('/api/reviews', 'POST', review(catalog.find(m => m.priority).id, 'collection'), cookie)).status, 201);
const restored = await (await call('/api/session', 'GET', undefined, cookie)).json();
assert.equal(restored.submissions.length, 7);
assert.equal(restored.profile.language, 'ru');
assert.equal((await call('/api/reviews', 'GET', undefined, otherCookie)).status, 404);
assert.equal((await call('/api/profile', 'PUT', { ...profile, name: 'x'.repeat(21000) }, cookie)).status, 413);
console.log('Passed: actual SQLite migrations, secure sessions, profile persistence, private reads, cross-origin denial, server validation, calibration gate, retry deduplication, restored reviews, request size limit.');

// Owner permissions use only the platform-authenticated identity, never a FAF
// nickname or the ordinary participant session.
env.OWNER_EMAIL = 'owner@example.test';
const ownerHeaders = { 'oai-authenticated-user-id': 'site-scoped-owner', 'oai-authenticated-user-email': 'owner@example.test' };
async function ownerCall(path, headers = ownerHeaders, extraEnv = {}) {
  return worker.fetch(new Request(`https://example.test${path}`, { headers }), { ...env, ...extraEnv });
}
for (const path of ['/api/owner/snapshot','/api/owner/reviews?through=999','/api/owner/participants?through=999']) {
  assert.equal((await ownerCall(path, {})).status, 401);
  assert.equal((await ownerCall(path, { Cookie: cookie })).status, 401);
  assert.equal((await ownerCall(path, { ...ownerHeaders, 'oai-authenticated-user-email': 'other@example.test' })).status, 403);
  assert.equal((await ownerCall(path, ownerHeaders, { OWNER_EMAIL: undefined })).status, 403);
}
assert.equal((await ownerCall('/api/owner/snapshot',ownerHeaders,{OWNER_USER_ID:'different-owner'})).status,403);
assert.equal((await ownerCall('/api/owner/snapshot',ownerHeaders,{OWNER_USER_ID:'site-scoped-owner'})).status,200);
assert.equal((await ownerCall('/api/owner/reviews?through=-1')).status,400);
assert.equal((await ownerCall('/api/owner/reviews?through=999&after=1.5')).status,400);
for (let i=0;i<510;i++) {
  const r={...submission,id:crypto.randomUUID(),respondentId:state.respondentId};
  db.prepare('INSERT INTO reviews (id,participant_id,map_id,phase,payload,received_at) VALUES (?,?,?,?,?,?)').run(r.id,state.respondentId,r.mapId,r.phase,JSON.stringify(r),new Date().toISOString());
}
const snapshot = await (await ownerCall('/api/owner/snapshot')).json();
assert.equal(snapshot.reviews.count,517);
const later={...submission,id:crypto.randomUUID()};
db.prepare('INSERT INTO reviews (id,participant_id,map_id,phase,payload,received_at) VALUES (?,?,?,?,?,?)').run(later.id,state.respondentId,later.mapId,later.phase,JSON.stringify(later),new Date().toISOString());
let cursor=0;const all=[];
do {
  const page=await (await ownerCall(`/api/owner/reviews?through=${snapshot.reviews.through}&after=${cursor}`)).json();
  all.push(...page.rows);if(page.next===null)break;assert.ok(page.next>cursor);cursor=page.next;
}while(true);
assert.equal(all.length,517);
assert.equal(new Set(all.map(r=>r.id)).size,517);
assert.ok(all.every(r=>r.mapName&&r.receivedAt));
const people=await (await ownerCall(`/api/owner/participants?through=${snapshot.participants.through}`)).json();
assert.equal(people.rows.length,2);
assert.deepEqual(Object.keys(people.rows[0]).sort(),['createdAt','id','profile']);
assert.ok(!JSON.stringify(people).includes('token_hash'));
await build({entryPoints:['src/lib/owner-data.ts'],outfile:'.tmp/owner-data.mjs',bundle:true,format:'esm',platform:'node'});
const {aggregateMaps,reviewsCsv}=await import('../.tmp/owner-data.mjs');
const example={...all[0],profile:{...all[0].profile,name:'=HYPERLINK("bad")'},answers:{...all[0].answers,quality:5},note:'line one, "quoted"\nline two'};
const unknown={...example,id:crypto.randomUUID(),answers:{...example.answers,quality:'unknown'}};
const low={...example,id:crypto.randomUUID(),answers:{...example.answers,quality:1}};
const aggregate=aggregateMaps([example,unknown,low])[0];
assert.equal(aggregate.answers.quality.mean,3);assert.equal(aggregate.answers.quality.n,2);assert.equal(aggregate.answers.quality.spread,4);
const csv=reviewsCsv([example]);
assert.ok(csv.includes("'=HYPERLINK"));assert.ok(csv.includes('"line one, ""quoted""\nline two"'));assert.ok(csv.startsWith('\ufeff'));
console.log('Passed: owner-only reads, fail-closed authorization, pinned owner identity, complete 517-row snapshot pagination during new submissions, credential-free profile export, unknown-excluding averages, disagreement spread, and CSV injection/escaping.');
