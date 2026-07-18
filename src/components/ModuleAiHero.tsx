import clsx from 'clsx';
import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import {
  BarChart3,
  BrainCircuit,
  Database,
  LineChart,
} from 'lucide-react';
import type { PortalModuleTheme } from '@/lib/moduleFromPageId';
import { t } from '@/i18n';

type ChipDef = { key: string; Icon: LucideIcon; tone: string };

type ModuleVisualConfig = {
  stripMod: string;
  orbGradient: string;
  liveKey: string;
  pipelineLabelKey: string;
  sourceChips: ChipDef[];
};

const MODULE_VISUALS: Record<PortalModuleTheme, ModuleVisualConfig> = {
  bi: {
    stripMod: 'module-hero-strip--bi',
    orbGradient: 'from-sky-500 via-indigo-600 to-violet-600',
    liveKey: 'bi.hero.engineLive',
    pipelineLabelKey: 'bi.hero.pipelineLabel',
    sourceChips: [
      { key: 'bi.hero.chipSql', Icon: Database, tone: 'from-indigo-500/20 to-indigo-600/10 border-indigo-200/70 text-indigo-800' },
      { key: 'bi.hero.chipMetrics', Icon: BarChart3, tone: 'from-sky-500/20 to-sky-600/10 border-sky-200/70 text-sky-800' },
      { key: 'bi.hero.chipModels', Icon: LineChart, tone: 'from-violet-500/20 to-violet-600/10 border-violet-200/70 text-violet-800' },
    ],
  },
  settings: {
    stripMod: 'module-hero-strip--settings',
    orbGradient: 'from-violet-500 via-indigo-500 to-sky-500',
    liveKey: 'settings.hero.engineLive',
    pipelineLabelKey: 'settings.hero.pipelineLabel',
    sourceChips: [],
  },
};

type Props = {
  module: PortalModuleTheme;
  size?: 'dashboard' | 'page';
  titleKey: string;
  subtitleKey: string;
  descriptionKey?: string;
  /** Optional control(s) for the hero top-right (e.g. blinking first-value cue). */
  trailing?: ReactNode;
};

export default function ModuleAiHero({ module, size = 'page', titleKey, subtitleKey, trailing }: Props) {
  const cfg = MODULE_VISUALS[module];
  const isDashboard = size === 'dashboard';

  return (
    <header
      className={clsx(
        'module-hero-strip animate-fade-in',
        cfg.stripMod,
        isDashboard && 'module-hero-strip--dashboard',
      )}
    >
      <div className="module-hero-strip-main">
        <div className={clsx('module-hero-strip-icon bg-gradient-to-br', cfg.orbGradient)} aria-hidden>
          <BrainCircuit className="h-4 w-4" />
        </div>
        <div className="module-hero-strip-text min-w-0 flex-1">
          <h1 className="module-hero-strip-title">{t(titleKey)}</h1>
          <p className="module-hero-strip-subtitle">{t(subtitleKey)}</p>
        </div>
        <div className="module-hero-strip-trailing">
          {trailing}
          {isDashboard && (
            <span className="module-hero-strip-live" title={t(cfg.liveKey)}>
              <span className="module-hero-live-dot" aria-hidden />
              <span className="hidden sm:inline">{t(cfg.liveKey)}</span>
            </span>
          )}
        </div>
      </div>

      {isDashboard && cfg.sourceChips.length > 0 && (
        <div className="module-hero-strip-chips" aria-label={t(cfg.pipelineLabelKey)}>
          {cfg.sourceChips.map(({ key, Icon, tone }) => (
            <span key={key} className={clsx('module-hero-chip module-hero-chip-sm bg-gradient-to-br', tone)}>
              <Icon className="h-3 w-3 shrink-0 opacity-80" />
              {t(key)}
            </span>
          ))}
        </div>
      )}
    </header>
  );
}
