import { Navigate, Outlet, useLocation } from 'react-router-dom';
import PortalAuthGate from '@/components/PortalAuthGate';
import { useAuth } from '@/context/AuthContext';
import { firstInAppModulePath } from '@/lib/portalModules';
import { MODULE_HOME, moduleFromPath } from '@/lib/moduleRoutes';
import { t } from '@/i18n';

function AuthLoading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-violet-100 via-white to-sky-100 text-slate-500">
      {t('common.loading')}
    </div>
  );
}

export function RequirePortalSession() {
  const { portalUsersEnabled, user, ready, hasModule } = useAuth();
  const location = useLocation();

  if (!ready) return <AuthLoading />;
  if (portalUsersEnabled && !user) {
    if (location.pathname === '/settings') return <Outlet />;
    return <PortalAuthGate />;
  }

  const module = moduleFromPath(location.pathname);
  if (module && !hasModule(module)) {
    return <Navigate to={firstInAppModulePath(hasModule, MODULE_HOME)} replace />;
  }
  return <Outlet />;
}

export function RequireUserAdmin() {
  const { isUserAdmin, portalUsersEnabled, user, ready } = useAuth();
  if (!ready) return <AuthLoading />;
  if (portalUsersEnabled && !user) return <PortalAuthGate />;
  if (portalUsersEnabled && !isUserAdmin) return <Navigate to="/settings" replace />;
  return <Outlet />;
}
