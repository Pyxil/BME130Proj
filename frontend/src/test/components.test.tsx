import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PhonemeBreakdown } from "../components/PhonemeBreakdown";
import { ResultsPanel } from "../components/ResultsPanel";
import fixtures from "../mocks/fixtures.json";
import type { AnalysisResult, FeedbackResponse } from "../types";

// Real responses recorded from the backend (see backend/scripts/generate_frontend_fixtures.py)
const samples = (fixtures as unknown as { samples: Record<string, { analysis: AnalysisResult; feedback: FeedbackResponse }> }).samples;

describe("ResultsPanel", () => {
  it("shows the score, part-by-part comparison, issues and grounded feedback for an assessed attempt", () => {
    const { analysis, feedback } = samples.rabbit_r_as_w;
    render(<ResultsPanel result={analysis} feedback={feedback} feedbackLoading={false} />);
    expect(screen.getByRole("heading", { name: `Pronunciation score: ${analysis.overall_score}/100` })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "How closely each part of the word matched the example" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /loudness over time for your recording and the example/ })).toBeInTheDocument();
    expect(screen.getByText("Common mistakes checked")).toBeInTheDocument();
    expect(screen.getAllByText(/may have sounded more like \/w\//).length).toBeGreaterThan(0);
    expect(screen.getByText(feedback.summary)).toBeInTheDocument();
    expect(screen.getByText(/not a clinical assessment/)).toBeInTheDocument();
  });

  it("asks for a new recording instead of showing a score when quality is too low", () => {
    const { analysis } = samples.quality_noisy;
    expect(analysis.status).toBe("retry_required");
    render(<ResultsPanel result={analysis} feedback={null} feedbackLoading={false} />);
    expect(screen.getByText("Please record again")).toBeInTheDocument();
    expect(screen.queryByText(/Pronunciation score:/)).not.toBeInTheDocument();
  });
});

describe("PhonemeBreakdown", () => {
  it("announces each sound's score and status to screen readers", () => {
    render(<PhonemeBreakdown phonemes={[
      { index: 0, phoneme: "r", arpabet: "R", score: 52, posterior: 0.01, status: "poor", likely_realization: "w" },
      { index: 1, phoneme: "æ", arpabet: "AE1", score: 97, posterior: 0.99, status: "good" },
    ]} />);
    expect(screen.getByText(/out of 100, needs work/)).toBeInTheDocument();
    expect(screen.getByText(/out of 100, clear/)).toBeInTheDocument();
    expect(screen.getByText("/w/")).toBeInTheDocument();
  });
});
