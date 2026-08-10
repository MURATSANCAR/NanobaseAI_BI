import { Suspense, lazy, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import ErrorBoundary from '@/components/ErrorBoundary';
import Layout from '@/components/Layout';
import { RequirePortalSession } from '@/components/RequireAuth';
import { t } from '@/i18n';

const BiSupersetPage = lazy(() => import('@/pages/BiSupersetPage'));
const BiSettingsPage = lazy(() => import('@/pages/BiSettingsPage'));
const BiChatPage = lazy(() => import('@/pages/BiChatPage'));
const BiSharesPage = lazy(() => import('@/pages/BiSharesPage'));
const BiSchedulesPage = lazy(() => import('@/pages/BiSchedulesPage'));
const BiAlertsPage = lazy(() => import('@/pages/BiAlertsPage'));
const BiBudgetPage = lazy(() => import('@/pages/BiBudgetPage'));
const BiAuditPage = lazy(() => import('@/pages/BiAuditPage'));
const BiGlossaryPage = lazy(() => import('@/pages/BiGlossaryPage'));
const BiSemanticCatalogPage = lazy(() => import('@/pages/BiSemanticCatalogPage'));
const BiScenarioReviewsPage = lazy(() => import('@/pages/BiScenarioReviewsPage'));
const BiTemplatesPage = lazy(() => import('@/pages/BiTemplatesPage'));
const BiQueriesPage = lazy(() => import('@/pages/BiQueriesPage'));
const BiConnectionPage = lazy(() => import('@/pages/BiConnectionPage'));
const BiSchemaPage = lazy(() => import('@/pages/BiSchemaPage'));
const BiPublicPage = lazy(() => import('@/pages/BiPublicPage'));

function RouteFallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center text-slate-500">
      {t('common.loading')}
    </div>
  );
}

/** Page-crash containment; the key resets the boundary on navigation. */
function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const location = useLocation();
  return <ErrorBoundary key={location.pathname}>{children}</ErrorBoundary>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<RouteFallback />}>
        <RoutedErrorBoundary>
        <Routes>
          <Route path="/" element={<Navigate to="/bi" replace />} />
          <Route path="login" element={<Navigate to="/bi" replace />} />
          <Route path="bi/public/:token" element={<BiPublicPage />} />

          <Route element={<RequirePortalSession />}>
            <Route element={<Layout />}>
              <Route path="bi" element={<BiSupersetPage />} />
              <Route path="bi/projects" element={<Navigate to="/bi" replace />} />
              <Route path="bi/sources" element={<BiConnectionPage />} />
              <Route path="bi/settings" element={<BiSettingsPage />} />
              <Route path="bi/chat" element={<BiChatPage />} />
              <Route path="bi/analytics" element={<Navigate to="/bi" replace />} />
              <Route path="bi/superset" element={<Navigate to="/bi" replace />} />
              <Route path="bi/dashboard" element={<Navigate to="/bi" replace />} />
              <Route path="bi/reports" element={<Navigate to="/bi" replace />} />
              <Route path="bi/schema" element={<BiSchemaPage />} />
              <Route path="bi/schedules" element={<BiSchedulesPage />} />
              <Route path="bi/queries" element={<BiQueriesPage />} />
              <Route path="bi/templates" element={<BiTemplatesPage />} />
              <Route path="bi/glossary" element={<BiGlossaryPage />} />
              <Route path="bi/semantic-catalog" element={<BiSemanticCatalogPage />} />
              <Route path="bi/scenario-reviews" element={<BiScenarioReviewsPage />} />
              <Route path="bi/alerts" element={<BiAlertsPage />} />
              <Route path="bi/budget" element={<BiBudgetPage />} />
              <Route path="bi/shares" element={<BiSharesPage />} />
              <Route path="bi/audit" element={<BiAuditPage />} />
              <Route path="bi/connection" element={<BiConnectionPage />} />
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/bi" replace />} />
        </Routes>
        </RoutedErrorBoundary>
      </Suspense>
    </BrowserRouter>
  );
}
