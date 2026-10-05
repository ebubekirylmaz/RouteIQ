import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { HistoryPage } from "./pages/HistoryPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ReviewQueuePage } from "./pages/ReviewQueuePage";
import { TryItPage } from "./pages/TryItPage";

// The charts bring the chart library, which is most of the weight of the app. It loads only
// when somebody opens the screen, so the review queue stays quick to open.
const ChartsPage = lazy(() => import("./pages/ChartsPage").then((module) => ({ default: module.ChartsPage })));

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="review" replace />} />
        <Route path="review" element={<ReviewQueuePage />} />
        <Route path="overview" element={<OverviewPage />} />
        <Route
          path="charts"
          element={
            <Suspense
              fallback={
                <p role="status" aria-label="Loading">
                  Loading the charts…
                </p>
              }
            >
              <ChartsPage />
            </Suspense>
          }
        />
        <Route path="history" element={<HistoryPage />} />
        <Route path="try" element={<TryItPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
