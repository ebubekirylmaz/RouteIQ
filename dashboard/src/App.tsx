import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { ChartsPage } from "./pages/ChartsPage";
import { HistoryPage } from "./pages/HistoryPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ReviewQueuePage } from "./pages/ReviewQueuePage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="review" replace />} />
        <Route path="review" element={<ReviewQueuePage />} />
        <Route path="overview" element={<OverviewPage />} />
        <Route path="charts" element={<ChartsPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
