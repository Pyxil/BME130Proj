import type {
  AttemptList, AttemptOut, FeedbackResponse, PhonemeOption, ProgressOut, SessionCreate, SessionOut,
  SessionSummary, SystemStatus, TokenResponse, User, UserUpdate, WordDetail, WordList,
} from "../types";
import { request } from "./api";

export const api = {
  register: (email: string, password: string, display_name: string) =>
    request<TokenResponse>("/api/auth/register", { json: { email, password, display_name } }),
  login: (email: string, password: string) => request<TokenResponse>("/api/auth/login", { json: { email, password } }),
  me: () => request<User>("/api/users/me"),
  updateMe: (patch: UserUpdate) => request<User>("/api/users/me", { method: "PATCH", json: patch }),
  deleteRecordings: () => request<{ deleted: number }>("/api/users/me/recordings", { method: "DELETE" }),
  deleteData: () => request<void>("/api/users/me/data", { method: "DELETE" }),
  deleteAccount: () => request<void>("/api/users/me", { method: "DELETE" }),
  exportData: () => request<unknown>("/api/users/me/export"),

  words: (query: { difficulty?: string; phoneme?: string; q?: string; limit?: number } = {}) =>
    request<WordList>("/api/words", { query }),
  word: (id: number) => request<WordDetail>(`/api/words/${id}`),
  phonemes: () => request<PhonemeOption[]>("/api/words/phonemes"),
  wordAudioUrl: (id: number, variant: string, slow: boolean) =>
    `/api/words/${id}/audio?variant=${encodeURIComponent(variant)}&speed=${slow ? "slow" : "normal"}`,

  createSession: (body: SessionCreate) => request<SessionOut>("/api/sessions", { json: body }),
  session: (id: string) => request<SessionOut>(`/api/sessions/${id}`),
  sessions: () => request<SessionSummary[]>("/api/sessions"),
  advance: (id: string, index?: number) =>
    request<SessionOut>(`/api/sessions/${id}/advance`, { json: index === undefined ? {} : { current_index: index } }),
  complete: (id: string) => request<SessionOut>(`/api/sessions/${id}/complete`, { method: "POST" }),

  analyze: (wav: Blob, wordId: number, sessionId: string | null, store: boolean, signal?: AbortSignal) => {
    const form = new FormData();
    form.append("audio", wav, "recording.wav");
    form.append("word_id", String(wordId));
    if (sessionId) form.append("session_id", sessionId);
    form.append("store_recording", store ? "true" : "false");
    return request<AttemptOut>("/api/pronunciation/analyze", { form, signal });
  },
  feedback: (attemptId: string) => request<FeedbackResponse>("/api/feedback", { json: { attempt_id: attemptId } }),
  attempts: (query: { word_id?: number; limit?: number; offset?: number } = {}) =>
    request<AttemptList>("/api/attempts", { query }),
  attempt: (id: string) => request<AttemptOut>(`/api/attempts/${id}`),
  recordingResponse: (id: string) => request<Response>(`/api/attempts/${id}/recording`, { raw: true }),
  deleteRecording: (id: string) => request<void>(`/api/attempts/${id}/recording`, { method: "DELETE" }),

  progress: () => request<ProgressOut>("/api/users/me/progress"),
  status: () => request<SystemStatus>("/api/system/status"),
};
