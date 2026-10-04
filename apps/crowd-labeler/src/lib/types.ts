export type QuestionType = "scale" | "multi_choice" | "single_choice" | "text";

export type Familiarity = "never_played" | "seen_it" | "played_casually" | "know_it_well";

export type MapRecord = {
  id: string;
  mapDir: string;
  canonicalName: string;
  version: string;
  sizeX: number | null;
  sizeZ: number | null;
  playerCount: number | null;
  inventorySource: string;
  previewUrl: string | null;
  structuralPreviewUrl: string | null;
  hasPreview: boolean;
};

export type QuestionDefinition = {
  id: string;
  key: string;
  prompt: string;
  questionType: QuestionType;
  scaleMin?: number;
  scaleMax?: number;
  category: "gameplay" | "structure" | "quality" | "aesthetic" | "respondent";
  options?: string[];
  active: boolean;
};

export type Respondent = {
  id: string;
  anonymousKey: string;
  displayName: string;
  createdAt: string;
  lastSeenAt: string;
};

export type DraftAnswer = {
  questionId: string;
  unknown: boolean;
  numericValue: number | null;
  choiceValues: string[];
  textValue: string;
};

export type ResponseRow = {
  id: string;
  mapId: string;
  respondentId: string;
  questionId: string;
  numericValue: number | null;
  choiceValues: string[];
  textValue: string;
  unknown: boolean;
  familiarity: Familiarity;
  clientSessionId: string;
  createdAt: string;
};

export type AggregatedLabel = {
  mapId: string;
  questionKey: string;
  responseCount: number;
  mean: number | null;
  median: number | null;
  stddev: number | null;
  unknownCount: number;
  weightedMean: number | null;
  updatedAt: string;
};
