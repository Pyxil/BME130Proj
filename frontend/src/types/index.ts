/**
 * Friendly aliases for the types generated from the backend OpenAPI contract
 * (`npm run gen:api` regenerates api.generated.ts from ../docs/openapi.json).
 * Never edit api.generated.ts by hand.
 */
import type { components } from "./api.generated";

type S = components["schemas"];

export type User = S["UserOut"];
export type UserUpdate = S["UserUpdate"];
export type TokenResponse = S["TokenResponse"];
export type WordSummary = S["WordSummary"];
export type WordDetail = S["WordDetail"];
export type WordList = S["WordList"];
export type PhonemeOption = S["PhonemeOption"];
export type SessionOut = S["SessionOut"];
export type SessionCreate = S["SessionCreate"];
export type SessionMode = NonNullable<S["SessionCreate"]["mode"]>;
export type SessionSummary = S["SessionSummary"];
export type SessionWordProgress = S["SessionWordProgress"];
export type AttemptOut = S["AttemptOut"];
export type AttemptSummary = S["AttemptSummary"];
export type AttemptList = S["AttemptList"];
export type AnalysisResult = S["AnalysisResult"];
export type PhonemeScore = S["PhonemeScore"];
export type Issue = S["Issue"];
export type Strength = S["Strength"];
export type ComponentScore = S["ComponentScore"];
export type FeedbackResponse = S["FeedbackResponse"];
export type ProgressOut = S["ProgressOut"];
export type PhonemeStat = S["PhonemeStat"];
export type SystemStatus = S["SystemStatus"];
export type SignalAnalysis = S["SignalAnalysis"];
export type SignalPart = S["SignalPart"];
export type MistakeCheck = S["MistakeCheck"];
