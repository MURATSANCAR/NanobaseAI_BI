import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import StitchCanvas from '@/canvas/stitch/StitchCanvas';
import { ZOOM_MAX, ZOOM_MIN } from '../canvas/stitch/Shell';
import Shell from '@/canvas/stitch/Shell';
import Splash, { markSplashSeen, splashSeen } from '@/canvas/stitch/Splash';
import SessionGate from '@/canvas/stitch/SessionGate';
import { alertsData, cfoData, schedulesData } from '@/canvas/stitch/screens';
import { useCfoData } from '@/canvas/cfo';
import { ENGINE_ENABLED, EngineAuthError, ask as askEngine, boardApi, type AskAnswer } from '@/canvas/engine';
import { fromDto, newId, nextSlot, topZ, type BoardCard } from '@/canvas/board/store';
import type { BoardAction } from '@/canvas/stitch/data';
import { useQueryClient } from '@tanstack/react-query';
import { summarizeAlerts, summarizeSchedules, useCanvasQueries } from '@/canvas/data';
import AlertsPanel, { parseRule, type RuleDraft } from '@/canvas/alerts/AlertsPanel';

/** Yol parçası → ekran. Yeni ekran eklemek bu listeye bir satır eklemektir. */
const SCREENS = ['planli-raporlar', 'uyarilar'] as const;
type ScreenId = (typeof SCREENS)[number];
const isScreen = (v: string | undefined): v is ScreenId => SCREENS.includes((v ?? '') as ScreenId);


export default function BiCanvasPage() {
  // Ekran yolun son parçasından okunur: /timas/uyarilar → 'uyarilar'.
  const { pathname } = useLocation();
  const screen = pathname.split('/').filter(Boolean).pop();
  // Uyarılar paneli adresten açılır: ?panel=kurallar | ?panel=yeni. Geri tuşu paneli kapatır.
  const [params, setParams] = useSearchParams();
  const panelParam = params.get('panel');
  const panel = panelParam === 'kurallar' || panelParam === 'yeni' ? panelParam : null;
  const [draft, setDraft] = useState<RuleDraft | null>(null);

  const { schedules, alerts } = useCanvasQueries();
  const qc = useQueryClient();
  const cfo = useCfoData();

  const sched = useMemo(() => summarizeSchedules(schedules.data?.schedules ?? []), [schedules.data]);
  const alert = useMemo(() => summarizeAlerts(alerts.data?.alerts ?? [], alerts.data?.email), [alerts.data]);
  const source = ENGINE_ENABLED ? 'Canlı veri' : 'Bağlantı yok';

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
      // Genel bakış CFO ekranıdır. Motor yolu yoksa
      // portal özetine düşer.
      return { ...cfoData(cfo, source), zoom: z };
    }
    if (screen === 'planli-raporlar') return { ...schedulesData(sched, schedules.isLoading, source), zoom: z };
    return { ...alertsData(alert, alerts.isLoading, source), zoom: z };
  }, [
    screen,
    cfo,
    sched,
    alert,
    source,
    zoom,
    schedules.isLoading,
    alerts.isLoading,
  ]);

  // Soru kutusu başka ürüne gitmez: cevap kanvasın kendi karar kartına düşer.
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [asking, setAsking] = useState(false);
  const [askErr, setAskErr] = useState<string | null>(null);
  /** Cevabı doğuran soru; panoya eklenen kartın başlığı ve yeniden sorulacak sorusu olur. */
  const [answeredQ, setAnsweredQ] = useState('');
  const [board, setBoard] = useState<{ state: BoardAction['state']; message?: string }>({ state: 'idle' });
  // Ardışık sorular kuyruğa girer ve tek tek işlenir; yeni soru önceki cevabı ezmez.
  const queueRef = useRef<string[]>([]);
  const runningRef = useRef(false);
  const [queued, setQueued] = useState(0);
  const [current, setCurrent] = useState<string | null>(null);
  const runNext = () => {
    const q = queueRef.current.shift();
    setQueued(queueRef.current.length);
    if (q === undefined) {
      runningRef.current = false;
      setAsking(false);
      setCurrent(null);
      return;
    }
    runningRef.current = true;
    setAsking(true);
    setCurrent(q);
    setAskErr(null);
    setAnswer(null);
    setBoard({ state: 'idle' });
    askEngine(q)
      .then((a) => {
        setAnsweredQ(q);
        setAnswer({ ...a, summary: a.summary ?? a.explanation });
      })
      .catch((e) => setAskErr(e instanceof EngineAuthError ? 'Oturum gerekli' : 'Zeki AI yanıt vermedi'))
      .finally(() => runNext());
  };
  const ask = (q: string) => {
    if (!ENGINE_ENABLED) return;
    queueRef.current.push(q);
    setQueued(queueRef.current.length);
    if (!runningRef.current) runNext();
  };

  // Yanıt beklenirken sırayla ilerleyen tema uyumlu ifadeler.
  const PHASES = ['Zeki düşünüyor', 'Veriyi buldu', 'Hesaplıyor', 'Özetliyor'];
  const [phase, setPhase] = useState(0);
  useEffect(() => {
    if (!current) {
      setPhase(0);
      return;
    }
    setPhase(0);
    const id = window.setInterval(() => setPhase((p) => Math.min(p + 1, PHASES.length - 1)), 1000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current]);

  // Kampüs sayfasındaki ZEKİ kutusu soruyu adresle getirir (?soru=…). Bir kez sorulur, sonra adresten silinir;
  // yenileme aynı soruyu motora ikinci kez göndermesin.
  const incoming = params.get('soru');
  useEffect(() => {
    if (!incoming) return;
    markSplashSeen();
    setSplash(false);
    setParams({}, { replace: true });
    ask(incoming);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incoming]);

  // Uyarılar ekranında soru çubuğu kural yazar: cümle taslağa çevrilir, kişi panelde düzeltip kaydeder.
  const onAsk = (q: string) => {
    if (screen === 'uyarilar') {
      setDraft(parseRule(q));
      setParams({ panel: 'yeni' });
      return;
    }
    ask(q);
  };

  // Sohbet cevabı → pano kartı. Doğrusu sunucudaki pano: önce güncel liste okunur (başka sekmede eklenen
  // kart ezilmesin), kart boş yere eklenir, sonra sonucu sunucuda hesaplanır ki pano açılınca hazır olsun.
  const addToBoard = async () => {
    const a = answer;
    if (!a?.sql || !a.records?.length || board.state === 'saving') return;
    setBoard({ state: 'saving' });
    try {
      // Grafik önerici recharts'ı getirir; genel bakış açılışını ağırlaştırmasın diye yalnız burada yüklenir.
      const [{ suggestChart }, current] = await Promise.all([import('@/canvas/board/Chart'), boardApi.load()]);
      const cards = current.cards.map(fromDto);
      const cols = (a.columns ?? []) as Array<{ name: string; type: string }>;
      const chart = suggestChart(cols, a.records as Array<Record<string, unknown>>);
      const card: BoardCard = {
        id: newId(),
        title: answeredQ,
        question: answeredQ,
        sql: a.sql,
        chart,
        depth: false,
        z: topZ(cards),
        refresh: 'manual',
        createdAt: new Date().toISOString(),
        ...nextSlot(cards),
      };
      await boardApi.save([...cards, card]);
      // Sunucu kartı bilmeden koşturamaz; kaydetmeden sonra. Koşu düşse de kart panoda, orada yeniden denenir.
      await boardApi.run(card.id).catch(() => undefined);
      setBoard({ state: 'done', message: chart });
    } catch (e) {
      setBoard({ state: 'error', message: e instanceof EngineAuthError ? 'Oturum gerekli' : 'Panoya eklenemedi' });
    }
  };

  const view = useMemo(() => {
    if (!answer && !asking && !askErr) return d;
    const rows = answer?.records?.length ?? 0;
    return {
      ...d,
      main: {
        ...d.main,
        subject: 'Verine sor',
        loading: asking,
        model: asking ? `${PHASES[phase]}…` : answer?.latency_ms ? `${(answer.latency_ms / 1000).toFixed(1)} sn` : '',
        text: asking
          ? `“${PHASES[phase]}…”`
          : askErr
            ? `“${askErr}.”`
            : `“${answer?.summary ?? 'Zeki AI özet üretmedi.'}”`,
        m1: { label: 'Satır:', value: String(rows) },
        m2: { label: 'Kolon:', value: String(answer?.columns?.length ?? 0) },
        m3: { label: 'Tip:', value: answer?.type ?? '—' },
        note: queued > 0 ? `${queued} soru sırada` : d.main.note,
        board: !asking && answer?.sql && (answer.records?.length ?? 0) > 0 ? { ...board, onAdd: () => void addToBoard() } : undefined,
        timing: !asking && answer?.records ? answer : null,
      },
      c5: {
        ...d.c5,
        title: 'Üretilen SQL',
        badge: askErr ? 'Hata' : asking ? 'Çalışıyor' : 'Canlı',
        summary: answer?.sql ?? (asking ? 'Bekleniyor…' : (askErr ?? '')),
        sql: answer?.sql,
        latency: answer?.latency_ms ? `${answer.latency_ms} ms` : '—',
        timing: !asking && answer?.records ? answer : null,
      },
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d, answer, asking, askErr, phase, queued, board, answeredQ]);

  if (splash) return <Splash onDone={closeSplash} />;

  // Motor 401 diyorsa veri gelmez; sebebini gizlemeyip giriş kapısını açıyoruz.
  const needsLogin = ENGINE_ENABLED && cfo.authRequired;

  return (
    <>
      {screen === 'uyarilar' ? (
        // Uyarılar ekranı şimdilik boş: yalnız kabuk (üst şerit + ray). İçerik ayrıca tasarlanacak.
        <Shell
          head={{ tenant: view.tenant, section: view.section, crumb: view.crumb, source: view.source, presence: view.presence, zoom: view.zoom }}
          rail={view.rail}
          onZoom={onZoom}
        >
          {null}
        </Shell>
      ) : (
        <StitchCanvas d={view} onAsk={onAsk} onZoom={onZoom} zoom={zoom} screen={screen ?? 'genel'} />
      )}
      {screen === 'uyarilar' && panel && (
        <AlertsPanel
          mode={panel}
          onMode={(m) => setParams({ panel: m })}
          onClose={() => {
            setParams({});
            setDraft(null);
          }}
          rules={alerts.data?.alerts ?? []}
          email={alerts.data?.email ?? { configured: false, sender: null }}
          draft={draft}
        />
      )}
      {needsLogin && <SessionGate onDone={() => qc.invalidateQueries()} />}
    </>
  );
}
