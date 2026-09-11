import { useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import StitchCanvas from '@/canvas/stitch/StitchCanvas';
import Splash, { markSplashSeen, splashSeen } from '@/canvas/stitch/Splash';
import SessionGate from '@/canvas/stitch/SessionGate';
import { alertsData, approvalsData, cfoData, glossaryData, schedulesData } from '@/canvas/stitch/screens';
import { useCfoData } from '@/canvas/cfo';
import {
  ENGINE_ENABLED,
  EngineAuthError,
  ask as askEngine,
  concepts as fetchConcepts,
  review as fetchReview,
  type AskAnswer,
} from '@/canvas/engine';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { summarizeAlerts, summarizeSchedules, useCanvasQueries } from '@/canvas/data';
import '@/canvas/canvas.css';

/** Yol parçası → ekran. Yeni ekran eklemek bu listeye bir satır eklemektir. */
const SCREENS = ['planli-raporlar', 'uyarilar', 'veri-sozlugu', 'onaylar'] as const;
type ScreenId = (typeof SCREENS)[number];
const isScreen = (v: string | undefined): v is ScreenId => SCREENS.includes((v ?? '') as ScreenId);

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 2;

export default function BiCanvasPage() {
  // Ekran yolun son parçasından okunur: /timas/uyarilar → 'uyarilar'.
  const { pathname } = useLocation();
  const screen = pathname.split('/').filter(Boolean).pop();

  const { on, schedules, alerts } = useCanvasQueries();
  const qc = useQueryClient();
  const cfo = useCfoData();

  // Sözlük ve onay kuyruğu motordan gelir; eski sistemdeki iki menünün karşılığı.
  const glossary = useQuery({
    queryKey: ['semantic-concepts'],
    queryFn: () => fetchConcepts(),
    enabled: ENGINE_ENABLED,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const approvals = useQuery({
    queryKey: ['semantic-review'],
    queryFn: () => fetchReview(),
    enabled: ENGINE_ENABLED,
    staleTime: 60_000,
    retry: false,
  });

  const sched = useMemo(() => summarizeSchedules(schedules.data?.schedules ?? []), [schedules.data]);
  const alert = useMemo(() => summarizeAlerts(alerts.data?.alerts ?? []), [alerts.data]);
  const source = ENGINE_ENABLED ? 'Logo · semantic bridge' : on ? 'Portal API · canlı' : 'Bağlantı yok';

  // Açılışta ZEKİ tam sayfada; oturum başına bir kez.
  const [splash, setSplash] = useState(() => !splashSeen());
  const closeSplash = () => {
    markSplashSeen();
    setSplash(false);
  };

  // Sığdırmayı kanvas kendi içinde yapar; burada yalnız yakınlaştırma tutulur.
  const [zoom, setZoom] = useState(1);
  const onZoom = (delta: number) =>
    setZoom((z) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Number((z + delta).toFixed(2)))));

  const d = useMemo(() => {
    const z = `%${Math.round(zoom * 100)}`;
    if (!isScreen(screen)) {
      // Genel bakış CFO ekranıdır: rakamlar Logo'dan gelir. Motor yolu yoksa
      // portal özetine düşer.
      return { ...cfoData(cfo, source), zoom: z };
    }
    if (screen === 'planli-raporlar') return { ...schedulesData(sched, schedules.isLoading, source), zoom: z };
    if (screen === 'uyarilar') return { ...alertsData(alert, alerts.isLoading, source), zoom: z };
    if (screen === 'veri-sozlugu')
      return {
        ...glossaryData(
          { data: glossary.data ?? null, loading: glossary.isLoading, authRequired: glossary.error instanceof EngineAuthError },
          source,
        ),
        zoom: z,
      };
    if (screen === 'onaylar')
      return {
        ...approvalsData(
          { data: approvals.data ?? null, loading: approvals.isLoading, authRequired: approvals.error instanceof EngineAuthError },
          source,
        ),
        zoom: z,
      };
    return { ...cfoData(cfo, source), zoom: z };
  }, [
    screen,
    cfo,
    sched,
    alert,
    source,
    zoom,
    glossary.data,
    glossary.isLoading,
    glossary.error,
    approvals.data,
    approvals.isLoading,
    approvals.error,
    schedules.isLoading,
    alerts.isLoading,
  ]);

  // Soru kutusu başka ürüne gitmez: cevap kanvasın kendi karar kartına düşer.
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [asking, setAsking] = useState(false);
  const [askErr, setAskErr] = useState<string | null>(null);
  const ask = (q: string) => {
    if (!ENGINE_ENABLED) return;
    setAsking(true);
    setAskErr(null);
    setAnswer(null);
    askEngine(q)
      .then((a) => setAnswer({ ...a, summary: a.summary ?? a.explanation }))
      .catch((e) => setAskErr(e instanceof EngineAuthError ? 'Oturum gerekli' : 'Motor yanıt vermedi'))
      .finally(() => setAsking(false));
  };

  const view = useMemo(() => {
    if (!answer && !asking && !askErr) return d;
    const rows = answer?.records?.length ?? 0;
    return {
      ...d,
      main: {
        ...d.main,
        subject: 'Verine sor',
        model: asking ? 'Motor çalışıyor…' : answer?.latency_ms ? `${(answer.latency_ms / 1000).toFixed(1)} sn` : '',
        text: asking
          ? '“Soru motora gönderildi…”'
          : askErr
            ? `“${askErr}.”`
            : `“${answer?.summary ?? 'Motor özet üretmedi.'}”`,
        m1: { label: 'Satır:', value: String(rows) },
        m2: { label: 'Kolon:', value: String(answer?.columns?.length ?? 0) },
        m3: { label: 'Tip:', value: answer?.type ?? '—' },
      },
      c5: {
        ...d.c5,
        title: 'Üretilen SQL',
        badge: askErr ? 'Hata' : asking ? 'Çalışıyor' : 'Canlı',
        summary: (answer?.sql ?? (asking ? 'Bekleniyor…' : (askErr ?? ''))).slice(0, 400),
        latency: answer?.latency_ms ? `${answer.latency_ms} ms` : '—',
      },
    };
  }, [d, answer, asking, askErr]);

  if (splash) return <Splash onDone={closeSplash} />;

  // Motor 401 diyorsa veri gelmez; sebebini gizlemeyip giriş kapısını açıyoruz.
  const needsLogin =
    ENGINE_ENABLED &&
    (cfo.authRequired || glossary.error instanceof EngineAuthError || approvals.error instanceof EngineAuthError);

  return (
    <>
      <StitchCanvas d={view} onAsk={ask} onZoom={onZoom} zoom={zoom} screen={screen ?? 'genel'} />
      {needsLogin && <SessionGate onDone={() => qc.invalidateQueries()} />}
    </>
  );
}
