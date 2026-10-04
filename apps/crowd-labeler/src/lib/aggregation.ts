import { FAMILIARITY_OPTIONS } from "../data/questions";
import type { AggregatedLabel, QuestionDefinition, ResponseRow } from "./types";

const median = (values: number[]) => {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const midpoint = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) return sorted[midpoint];
  return (sorted[midpoint - 1] + sorted[midpoint]) / 2;
};

const stddev = (values: number[], mean: number | null) => {
  if (values.length < 2 || mean === null) return null;
  const variance =
    values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
};

export function aggregateResponses(
  responses: ResponseRow[],
  questions: QuestionDefinition[],
): AggregatedLabel[] {
  const questionById = new Map(questions.map((question) => [question.id, question]));
  const buckets = new Map<string, ResponseRow[]>();

  for (const response of responses) {
    const question = questionById.get(response.questionId);
    if (!question || question.questionType !== "scale") continue;
    const key = `${response.mapId}:${question.key}`;
    buckets.set(key, [...(buckets.get(key) ?? []), response]);
  }

  const now = new Date().toISOString();
  return [...buckets.entries()].map(([key, rows]) => {
    const [mapId, questionKey] = key.split(":");
    const numericRows = rows.filter((row) => !row.unknown && row.numericValue !== null);
    const values = numericRows.map((row) => row.numericValue as number);
    const mean = values.length
      ? values.reduce((sum, value) => sum + value, 0) / values.length
      : null;

    let weightedMean: number | null = null;
    const weighted = numericRows.map((row) => {
      const weight =
        FAMILIARITY_OPTIONS.find((option) => option.value === row.familiarity)?.weight ?? 1;
      return { value: row.numericValue as number, weight };
    });
    const totalWeight = weighted.reduce((sum, row) => sum + row.weight, 0);
    if (totalWeight > 0) {
      weightedMean =
        weighted.reduce((sum, row) => sum + row.value * row.weight, 0) / totalWeight;
    }

    return {
      mapId,
      questionKey,
      responseCount: values.length,
      mean,
      median: median(values),
      stddev: stddev(values, mean),
      unknownCount: rows.filter((row) => row.unknown).length,
      weightedMean,
      updatedAt: now,
    };
  });
}
