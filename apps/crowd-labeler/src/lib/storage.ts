import type { QuestionDefinition, Respondent, ResponseRow } from "./types";

const RESPONDENT_KEY = "mapgen.crowdLabeler.respondent";
const RESPONSES_KEY = "mapgen.crowdLabeler.responses";
const QUESTION_STATE_KEY = "mapgen.crowdLabeler.questionState";

const makeId = (prefix: string) => `${prefix}_${crypto.randomUUID()}`;

export function loadRespondent(): Respondent {
  const existing = localStorage.getItem(RESPONDENT_KEY);
  if (existing) {
    const respondent = JSON.parse(existing) as Respondent;
    const updated = { ...respondent, lastSeenAt: new Date().toISOString() };
    localStorage.setItem(RESPONDENT_KEY, JSON.stringify(updated));
    return updated;
  }

  const now = new Date().toISOString();
  const respondent: Respondent = {
    id: makeId("respondent"),
    anonymousKey: crypto.randomUUID(),
    displayName: "",
    createdAt: now,
    lastSeenAt: now,
  };
  localStorage.setItem(RESPONDENT_KEY, JSON.stringify(respondent));
  return respondent;
}

export function saveRespondent(respondent: Respondent): Respondent {
  const updated = { ...respondent, lastSeenAt: new Date().toISOString() };
  localStorage.setItem(RESPONDENT_KEY, JSON.stringify(updated));
  return updated;
}

export function loadResponses(): ResponseRow[] {
  const raw = localStorage.getItem(RESPONSES_KEY);
  return raw ? (JSON.parse(raw) as ResponseRow[]) : [];
}

export function appendResponses(nextRows: ResponseRow[]): ResponseRow[] {
  const rows = [...loadResponses(), ...nextRows];
  localStorage.setItem(RESPONSES_KEY, JSON.stringify(rows));
  return rows;
}

export function clearResponses(): ResponseRow[] {
  localStorage.removeItem(RESPONSES_KEY);
  return [];
}

export function loadQuestionState(defaultQuestions: QuestionDefinition[]): QuestionDefinition[] {
  const raw = localStorage.getItem(QUESTION_STATE_KEY);
  if (!raw) {
    return defaultQuestions;
  }

  const overrides = JSON.parse(raw) as Record<string, boolean>;
  return defaultQuestions.map((question) => ({
    ...question,
    active: overrides[question.id] ?? question.active,
  }));
}

export function saveQuestionState(questions: QuestionDefinition[]): QuestionDefinition[] {
  const overrides = Object.fromEntries(questions.map((question) => [question.id, question.active]));
  localStorage.setItem(QUESTION_STATE_KEY, JSON.stringify(overrides));
  return questions;
}
