import type { ReportOut } from "../api";
import "./TestReport.css";

const HEADLINE = {
  en: { passed: "Tested and ready", failed: "A person will check this game" },
  ur: { passed: "ٹیسٹ ہو گئی، تیار ہے", failed: "یہ گیم ہماری ٹیم دیکھے گی" },
} as const;

const SHOT_LABEL = { en: "See what the tester saw", ur: "ٹیسٹر نے کیا دیکھا" } as const;

function Mark({ passed }: { passed: boolean }) {
  return (
    <svg className="mark" viewBox="0 0 20 20" aria-hidden="true">
      {passed ? <path d="M5 10.5l3.2 3.2L15 7" /> : <path d="M6 6l8 8M14 6l-8 8" />}
    </svg>
  );
}

/** The play-test result in the shop's language: one line per check, with its evidence. */
const WORTH_CHECKING = { en: "Worth checking", ur: "ایک نظر دیکھ لیں" } as const;

export function TestReport({ report }: { report: ReportOut }) {
  const lang = report.language;
  const failedShot = report.gates.find((gate) => !gate.passed && gate.screenshot_url);
  const endCard = report.screenshots["phone-played-end"];
  return (
    <section
      className={`card test-report ${report.passed ? "is-passed" : "is-failed"}`}
      aria-labelledby="report-title"
      lang={lang}
      dir={lang === "ur" ? "rtl" : "ltr"}
    >
      <h2 id="report-title">{HEADLINE[lang][report.passed ? "passed" : "failed"]}</h2>
      <p className="report-summary">{report.summary}</p>

      <ul className="checks">
        {report.gates.map((gate) => (
          <li key={gate.gate} className={gate.passed ? "ok" : "bad"}>
            <Mark passed={gate.passed} />
            <span className="check-label">{gate.label}</span>
            {gate.passed ? null : (
              <span className="check-detail" lang="en" dir="ltr">
                {gate.message}
              </span>
            )}
          </li>
        ))}
      </ul>

      {failedShot?.screenshot_url || endCard ? (
        <a
          className="report-shot"
          href={failedShot?.screenshot_url ?? endCard}
          target="_blank"
          rel="noreferrer"
        >
          <img src={failedShot?.screenshot_url ?? endCard} alt="" loading="lazy" />
          <span>{SHOT_LABEL[lang]}</span>
        </a>
      ) : null}

      {report.warnings?.length ? (
        <div className="report-warnings">
          <h3>{WORTH_CHECKING[lang]}</h3>
          <ul>
            {report.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="report-next">{report.next_step}</p>
    </section>
  );
}
