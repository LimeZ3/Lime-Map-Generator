import type { Profile, State, Submission } from './survey';
export const hosted = import.meta.env.VITE_HOSTED === 'true';
async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const result = await fetch(path, { method, credentials: 'same-origin', headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
  if (!result.ok) throw new Error(result.status === 429 ? 'Too many requests. Please try again later.' : 'Could not save online. Your answers are still here. Please retry.');
  return result.json();
}
export const loadRemote = () => request<State>('/api/session');
export const saveRemoteProfile = (profile: Profile) => request<Profile>('/api/profile', 'PUT', profile);
export const saveRemoteReview = (review: Submission) => request<Submission>('/api/reviews', 'POST', review);
