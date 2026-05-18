import { useEffect, useState, useTransition, type FormEvent } from "react";
import { apiBaseUrl } from "./config";
import { HockeyOpsLogo } from "./components/HockeyOpsLogo";
import { CuratedSupportView, QueryExamples, ToolTrace } from "./components/SupportDataViews";
import {
  questionModeLabels,
  sampleQuestionsByMode,
  type QuestionMode,
} from "./constants/appConstants";
import { visibleLimitations } from "./utils/formatters";
import type { AskQuestionRequest, AskQuestionResponse, HealthResponse } from "./types/api";

const questionModes: QuestionMode[] = ["playerTeamInfo", "nhlRules"];

const questionPlaceholders: Record<QuestionMode, string> = {
  playerTeamInfo: "Compare two defensemen, ask for a player summary, or search for a contract profile.",
  nhlRules: "Ask about the CBA, rulebook, waivers, player movement, penalties, or roster rules.",
};

export default function App() {
  const [, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [questionMode, setQuestionMode] = useState<QuestionMode>("playerTeamInfo");
  const [question, setQuestion] = useState(sampleQuestionsByMode.playerTeamInfo[0]);
  const [result, setResult] = useState<AskQuestionResponse | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [, startTransition] = useTransition();
  const activeSampleQuestions = sampleQuestionsByMode[questionMode];
  const shownLimitations = result ? visibleLimitations(result.limitations) : [];

  useEffect(() => {
    let cancelled = false;

    async function loadHealth() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/health`);
        if (!response.ok) {
          throw new Error(`Healthcheck failed with ${response.status}.`);
        }

        const payload = (await response.json()) as HealthResponse;
        if (!cancelled) {
          setHealth(payload);
          setHealthError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setHealthError(error instanceof Error ? error.message : "Unknown healthcheck error.");
        }
      }
    }

    void loadHealth();

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      setSubmitError("Enter a hockey ops question first.");
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const response = await fetch(`${apiBaseUrl}/api/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question: trimmedQuestion } satisfies AskQuestionRequest),
      });

      const payload = (await response.json()) as AskQuestionResponse | { detail?: string };
      if (!response.ok) {
        throw new Error(
          "detail" in payload && payload.detail
            ? payload.detail
            : `Request failed with ${response.status}.`,
        );
      }

      startTransition(() => {
        setResult(payload as AskQuestionResponse);
      });
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Unknown request error.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function applySampleQuestion(nextQuestion: string) {
    setQuestion(nextQuestion);
    setSubmitError(null);
  }

  function applyQuestionMode(nextMode: QuestionMode) {
    setQuestionMode(nextMode);
    setQuestion(sampleQuestionsByMode[nextMode][0]);
    setSubmitError(null);
  }

  return (
    <main className="app-shell">
      <section className="hero">
        <div className="hero-copy">
          <div className="hero-brand">
            <HockeyOpsLogo className="hero-logo" />
          </div>
          <h1>Ask Hockey Questions.</h1>
          <p className="lede">Search, compare, and summarize players with contract context.</p>
        </div>
        <p className="hero-source-note">Data from NHL API, CapWages, & MoneyPuck.com</p>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-kicker">Question</p>
            <h2>What do you want to know?</h2>
          </div>
          <div className="question-mode-switch" aria-label="Question type">
            {questionModes.map((mode) => (
              <button
                key={mode}
                className={`mode-option${questionMode === mode ? " is-active" : ""}`}
                type="button"
                aria-pressed={questionMode === mode}
                onClick={() => applyQuestionMode(mode)}
              >
                {questionModeLabels[mode]}
              </button>
            ))}
          </div>
        </div>

        <form className="query-form" onSubmit={handleSubmit}>
          <label className="sr-only" htmlFor="question">
            {questionModeLabels[questionMode]} question
          </label>
          <textarea
            id="question"
            className="query-input"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder={questionPlaceholders[questionMode]}
            rows={4}
          />
          <div className="query-actions">
            <button
              className={`primary-button${isSubmitting ? " is-loading" : ""}`}
              type="submit"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <span className="button-loading">
                  <span className="button-spinner" aria-hidden="true" />
                  <span>Loading</span>
                </span>
              ) : (
                "Ask HockeyOps"
              )}
            </button>
          </div>
        </form>

        <QueryExamples questions={activeSampleQuestions} onSelect={applySampleQuestion} />

        {submitError ? <p className="error-banner">{submitError}</p> : null}
        {healthError ? <p className="error-banner">{healthError}</p> : null}
      </section>

      {result ? (
        <>
          {result.support_data.display_items.length > 0 ? (
            <CuratedSupportView
              displayItems={result.support_data.display_items}
              toolInvocations={result.support_data.tool_invocations}
            />
          ) : (
            <ToolTrace toolInvocations={result.support_data.tool_invocations} />
          )}

          <section className="panel answer-panel">
            <div className="panel-header">
              <div>
                <p className="section-kicker">Answer</p>
              </div>
            </div>

            <div className="answer-copy">{result.answer_text}</div>

            {shownLimitations.length > 0 ? (
              <div className="limitations-row">
                {shownLimitations.map((limitation) => (
                  <span key={limitation} className="limitation-pill">
                    {limitation}
                  </span>
                ))}
              </div>
            ) : null}
          </section>
        </>
      ) : null}
    </main>
  );
}
