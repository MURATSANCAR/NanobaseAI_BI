import { useEffect, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import clsx from 'clsx';
import { api, type ApiConfig } from '@/api/client';
import { getLocale, t } from '@/i18n';
import { brandText } from '@/utils/brand';

type BiAnalyticsEmbedProps = {
  config: ApiConfig;
  embedUuid: string;
  dashboardId: number;
  analyticsUrl: string;
  className?: string;
  /** When set, skip authenticated guest-token API (public share or prefetched token). */
  guestToken?: string;
};

function hasUsableSize(el: HTMLElement): boolean {
  return el.clientWidth >= 32 && el.clientHeight >= 64;
}

export default function BiSupersetEmbed({
  config,
  embedUuid,
  dashboardId,
  analyticsUrl,
  className,
  guestToken,
}: BiAnalyticsEmbedProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const locale = getLocale();

  useEffect(() => {
    const el = mountRef.current;
    if (!el || !embedUuid) return;

    let cancelled = false;
    let started = false;
    let observer: ResizeObserver | null = null;
    setLoading(true);
    setError(null);
    el.innerHTML = '';

    const runEmbed = async (force = false) => {
      if (cancelled || started) return;
      if (!force && !hasUsableSize(el)) return;
      started = true;
      observer?.disconnect();
      observer = null;

      try {
        const { embedDashboard } = await import('@superset-ui/embedded-sdk');
        if (cancelled) return;
        await embedDashboard({
          id: embedUuid,
          supersetDomain: analyticsUrl.replace(/\/$/, ''),
          mountPoint: el,
          fetchGuestToken: async () => {
            if (guestToken) return guestToken;
            const data = await api.bi.analytics.guestToken(config, dashboardId);
            return data.token;
          },
          dashboardUiConfig: {
            hideTitle: true,
            hideTab: true,
            hideChartControls: true,
            // Keep filters collapsed so charts stay in the first viewport (no buried widgets).
            filters: { expanded: false, visible: true },
            urlParams: {
              locale,
              standalone: '1',
            },
          },
        });
        if (!cancelled) setLoading(false);
      } catch (exc) {
        if (!cancelled) {
          setError(brandText(exc instanceof Error ? exc.message : String(exc)));
          setLoading(false);
        }
      }
    };

    if (hasUsableSize(el)) {
      void runEmbed();
    } else {
      observer = new ResizeObserver(() => {
        void runEmbed();
      });
      observer.observe(el);
      window.setTimeout(() => {
        if (cancelled || started) return;
        // Fill parent flex area — never force 70vh (that pushes charts below the fold).
        if (el.clientHeight < 64) {
          el.style.flex = '1 1 auto';
          el.style.minHeight = '0';
          el.style.height = '100%';
        }
        void runEmbed(true);
      }, 800);
    }

    return () => {
      cancelled = true;
      observer?.disconnect();
      if (el) el.innerHTML = '';
    };
  }, [config, dashboardId, embedUuid, analyticsUrl, locale, guestToken]);

  return (
    <div className={clsx('relative flex h-full min-h-0 w-full flex-col', className)}>
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center gap-2 bg-[#F5F5F5]/90 text-[#605E5C] backdrop-blur-sm">
          <Loader2 className="h-5 w-5 animate-spin" />
          {t('bi.analytics.loading')}
        </div>
      )}
      {error && (
        <div className="absolute left-3 right-3 top-3 z-20 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800 shadow-sm">
          {t('bi.analytics.embedError')}: {error}
        </div>
      )}
      <div
        ref={mountRef}
        className="bi-superset-embed-host h-full min-h-0 w-full flex-1 overflow-hidden [&>iframe]:block [&>iframe]:h-full [&>iframe]:min-h-0 [&>iframe]:w-full [&>iframe]:border-0"
      />
    </div>
  );
}
