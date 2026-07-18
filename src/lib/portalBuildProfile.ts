/** BI-only build profile helpers. */

export type BuildPortalModule = 'bi';

export function isBuildModuleEnabled(_module: BuildPortalModule = 'bi'): boolean {
  return true;
}

export function showModuleHub(): boolean {
  return false;
}

export function defaultAppPath(): string {
  return '/bi';
}
