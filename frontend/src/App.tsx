import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Spinner } from "./components/ui";
import { useAuth } from "./hooks/useAuth";
import AuthPage from "./pages/AuthPage";
import PracticeSetupPage from "./pages/PracticeSetupPage";

const ExercisePage = lazy(() => import("./pages/ExercisePage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const HistoryPage = lazy(() => import("./pages/HistoryPage"));
const AttemptDetailPage = lazy(() => import("./pages/AttemptDetailPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const AboutPage = lazy(() => import("./pages/AboutPage"));

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner label="Loading…" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

export default function App() {
  const { user } = useAuth();
  return (
    <Layout>
      <Suspense fallback={<Spinner label="Loading…" />}>
        <Routes>
          <Route path="/login" element={user ? <Navigate to="/practice" replace /> : <AuthPage mode="login" />} />
          <Route path="/register" element={user ? <Navigate to="/practice" replace /> : <AuthPage mode="register" />} />
          <Route path="/practice" element={<RequireAuth><PracticeSetupPage /></RequireAuth>} />
          <Route path="/practice/:sessionId" element={<RequireAuth><ExercisePage /></RequireAuth>} />
          <Route path="/dashboard" element={<RequireAuth><DashboardPage /></RequireAuth>} />
          <Route path="/history" element={<RequireAuth><HistoryPage /></RequireAuth>} />
          <Route path="/history/:attemptId" element={<RequireAuth><AttemptDetailPage /></RequireAuth>} />
          <Route path="/settings" element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="*" element={<Navigate to="/practice" replace />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}
