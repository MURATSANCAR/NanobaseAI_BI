export const DASHBOARD_PROJECT_KEY = 'nanobase_qa_dashboard_project';

function readDashboardProject(): string {
  try {
    return localStorage.getItem(DASHBOARD_PROJECT_KEY) || '';
  } catch {
    return '';
  }
}

export function setActiveProjectId(id: string, _opts?: { persistRemote?: boolean }): void {
  try {
    localStorage.setItem(DASHBOARD_PROJECT_KEY, id);
    window.dispatchEvent(new Event('nanobase-dashboard-project'));
  } catch {
    /* ignore */
  }
}

export function hydrateActiveProjectFromUser(
  _userOrProjectId?: { default_project_id?: string | null } | string | null,
): void {
  /* BI-only app has no QA project selector */
}

export function useActiveProjectId(): string {
  return readDashboardProject();
}
