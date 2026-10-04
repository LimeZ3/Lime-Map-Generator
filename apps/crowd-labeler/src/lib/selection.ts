import type { MapRecord, QuestionDefinition, ResponseRow } from "./types";

const hashText = (value: string) => {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
};

export function pickQuestionsForMap(
  map: MapRecord,
  questions: QuestionDefinition[],
  responses: ResponseRow[],
  respondentId: string,
  count = 3,
) {
  const activeQuestions = questions.filter((question) => question.active);
  const answeredByRespondent = new Set(
    responses
      .filter((row) => row.respondentId === respondentId && row.mapId === map.id)
      .map((row) => row.questionId),
  );

  return activeQuestions
    .map((question) => {
      const totalForMapQuestion = responses.filter(
        (row) => row.mapId === map.id && row.questionId === question.id,
      ).length;
      const stableJitter = hashText(`${map.id}:${question.id}`) / 2 ** 32;
      return {
        question,
        answered: answeredByRespondent.has(question.id),
        score: totalForMapQuestion + stableJitter,
      };
    })
    .filter((candidate) => !candidate.answered)
    .sort((a, b) => a.score - b.score)
    .slice(0, count)
    .map((candidate) => candidate.question);
}

export function pickNextMap(
  maps: MapRecord[],
  questions: QuestionDefinition[],
  responses: ResponseRow[],
  respondentId: string,
  previousMapId?: string,
) {
  const candidates = maps
    .map((map) => {
      const pendingQuestions = pickQuestionsForMap(map, questions, responses, respondentId, 3);
      const mapResponseCount = responses.filter((row) => row.mapId === map.id).length;
      const respondentMapCount = responses.filter(
        (row) => row.mapId === map.id && row.respondentId === respondentId,
      ).length;
      const rotationPenalty = previousMapId === map.id ? 1000 : 0;
      const stableJitter = hashText(`${respondentId}:${map.id}:${responses.length}`) / 2 ** 32;

      return {
        map,
        pendingQuestions,
        score: mapResponseCount + respondentMapCount * 4 + rotationPenalty + stableJitter,
      };
    })
    .filter((candidate) => candidate.pendingQuestions.length > 0)
    .sort((a, b) => a.score - b.score);

  return candidates[0] ?? null;
}
