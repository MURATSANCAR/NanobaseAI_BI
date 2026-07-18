/** Minimal test pipeline stubs for shared portal components in BI-only app. */

export function pipelineStepHref(to: string, _projectId?: string): string {
  return to;
}

export function pipelineIndexFromPath(_pathname: string, _search?: string): number | null {
  return null;
}

export function registryCaseHref(_testId: string, _projectId?: string): string {
  return '/bi';
}

export function suiteHref(_suiteId: string, _projectId?: string): string {
  return '/bi';
}

export function qualityMapHref(_projectId?: string): string {
  return '/bi';
}
