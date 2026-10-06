import { useMemo } from "react";

import { AccuracyChart } from "../components/evaluation/AccuracyChart";
import { CalibrationSection, CascadeTable, SetupsTable } from "../components/evaluation/EvaluationTables";
import { ChartCard } from "../components/charts/ChartCard";
import { useEvaluation } from "../hooks/useEvaluation";
import { accuracyRows, isNotAvailable } from "../lib/evaluation";
import { formatCount } from "../lib/format";
import styles from "./EvaluationPage.module.css";

/**
 * D6: how accurate, how expensive and how well calibrated the cascade is, measured offline on
 * labeled examples. It is not live traffic: live requests have no known right answer. Lazy-loaded,
 * because it brings the chart library.
 */
export function EvaluationPage() {
  const evaluation = useEvaluation();
  const report = evaluation.data;
  const rows = useMemo(() => (report ? accuracyRows(report.setups) : []), [report]);

  return (
    <section>
      <header className={styles.header}>
        <h1>Evaluation</h1>
      </header>

      {evaluation.isPending ? (
        <p role="status" aria-label="Loading">
          Loading the evaluation…
        </p>
      ) : !report ? (
        isNotAvailable(evaluation.error) ? (
          <p className={styles.empty}>
            No evaluation is available for this configuration. It needs recorded predictions of the baseline and the LLM tier on
            labeled examples.
          </p>
        ) : (
          <div className={styles.problem} role="alert">
            <span>The evaluation could not be loaded.</span>
            <button type="button" onClick={() => void evaluation.refetch()}>
              Try again
            </button>
          </div>
        )
      ) : (
        <>
          <p className={styles.sub}>
            Measured offline on the {report.split} split of “{report.domain}”: {formatCount(report.n)} examples with known labels. This is
            not live traffic, where the right answer is not known.
          </p>
          {report.data_source === "synthetic" && (
            <p className={styles.synthetic} role="note">
              The examples are synthetic, so these numbers say nothing about real data.
            </p>
          )}

          <ChartCard
            title="Accuracy"
            description={`The share of the ${formatCount(report.n)} examples that got the right label, with its 95% interval. The orange bar assumes every person is right.`}
          >
            <AccuracyChart rows={rows} />
          </ChartCard>

          <SetupsTable report={report} />
          <CascadeTable report={report} />
          <CalibrationSection report={report} />
        </>
      )}
    </section>
  );
}
