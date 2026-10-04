import { questions, legacyValue } from './survey';
import type { Submission, Profile, Settings } from './survey';
export type OwnerReview = Submission & { receivedAt: string; mapName: string; mapFolder: string };
export type Participant = { id: string; profile: Profile; createdAt: string };
export type Snapshot = { schemaVersion: number; exportedAt: string; reviews: { count: number; through: number }; participants: { count: number; through: number }; questionDefinitions: typeof questions; settings: Settings };
export type Dataset = Snapshot & { reviewRows: OwnerReview[]; participantRows: Participant[] };
export function score(s: Submission, key: string) { const value = s.answers[key]; return typeof value === 'number' ? s.scaleVersion === 5 ? value : legacyValue(value) : null; }
export function aggregateMaps(reviews: OwnerReview[]) {
  const grouped = new Map<string, OwnerReview[]>();
  for (const r of reviews) { const list = grouped.get(r.mapId) || []; list.push(r); grouped.set(r.mapId, list); }
  return Array.from(grouped, ([id, rows]) => ({ id, name: rows[0].mapName, count: rows.length, players: new Set(rows.map(r => r.respondentId)).size, answers: Object.fromEntries(questions.map(q => {
    const values = rows.map(r => score(r, q.id)).filter((v): v is number => v !== null);
    const mean = values.length ? values.reduce((a,b) => a+b,0) / values.length : null;
    return [q.id, { n: values.length, mean, spread: values.length > 1 ? Math.max(...values) - Math.min(...values) : null }];
  })) })).sort((a,b) => b.count-a.count || a.name.localeCompare(b.name));
}
export function reviewsCsv(rows: OwnerReview[]) {
  const keys = ['review_id','respondent_id','map_id','map_name','map_folder','map_version','phase','scale_version','calibration_revision','received_at','created_at','player_name','rating','rating_mode','experience','preferred_modes','language','familiarity','configuration','setup','seconds_spent','suggestions_shown',...questions.map(q => q.id),'biomes','unique_traits','unique_text','note'];
  const cell = (v: unknown) => {
    let s = v === null || v === undefined ? '' : String(v);
    // Untrusted comments and player names must not become spreadsheet formulas.
    if (typeof v === 'string' && /^[\s]*[=+\-@\t\r\n]/.test(s)) s = "'"+s;
    return '"'+s.replaceAll('"','""')+'"';
  };
  return '\ufeff'+[keys,...rows.map(r => [r.id,r.respondentId,r.mapId,r.mapName,r.mapFolder,r.mapVersion,r.phase,r.scaleVersion??4,r.calibrationRevision,r.receivedAt,r.createdAt,r.profile.name,r.profile.rating,r.profile.ratingMode,r.profile.experience,r.profile.modes.join('; '),r.profile.language||'en',r.familiarity,r.configuration,r.setup,r.secondsSpent,r.suggestionsShown,...questions.map(q=>r.answers[q.id]??'unknown'),r.biomes.join('; '),(r.uniqueTraits||[]).join('; '),r.uniqueText||'',r.note])].map(row=>row.map(cell).join(',')).join('\r\n');
}
