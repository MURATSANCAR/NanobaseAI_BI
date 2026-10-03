import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import StitchCanvas from '@/canvas/stitch/StitchCanvas';
import Shell, { ZOOM_MAX, ZOOM_MIN, ZoomStage } from '@/canvas/stitch/Shell';
import Splash, { markSplashSeen, splashSeen } from '@/canvas/stitch/Splash';
import SessionGate from '@/canvas/stitch/SessionGate';
import { alertsData, cfoData } from '@/canvas/stitch/screens';
import { useCfoData } from '@/canvas/cfo';
import { ENGINE_ENABLED, EngineAuthError, ask as askEngine, boardApi, type AskAnswer } from '@/canvas/engine';
import { fromDto, newId, nextSlot, topZ, type BoardCard } from '@/canvas/board/store';
import type { BoardAction } from '@/canvas/stitch/data';
import { toChips } from '@/canvas/interpret';
import { useQueryClient } from '@tanstack/react-query';
import { summarizeAlerts, useCanvasQueries } from '@/canvas/data';
import AlertsPanel from '@/canvas/alerts/AlertsPanel';
import { readableText } from '@/canvas/components/readableName';
import { moduleLabel } from '@/canvas/zekiAsk';
import { NAV, groupEntry } from '@/canvas/nav/navModel';
import { canOpenRoute, usePageAccess } from '@/canvas/useAdmin';

/** Cevabın geldiği modül: yalnız veriyle cevaplanmış soruda. Bağlantı kişinin açabildiği modül ekranına gider. */
function originOf(answer: AskAnswer | null, pages: ReturnType<typeof usePageAccess>): { label: string; topic: string; to?: string } | undefined {
  const cs = answer?.chatScope;
  const label = moduleLabel(cs?.module);
  if (!answer || (answer.type !== 'TEXT_TO_SQL' && answer.type !== 'PARTIAL_ANSWER') || !cs?.module || !label) return undefined;
  const group = NAV.find((g) => g.id === cs.module);
  const entry = group ? groupEntry(NAV, group) : null;
  return { label, topic: cs.topicLabel ?? '', to: entry && canOpenRoute(pages, entry) ? entry : undefined };
}

/** Bu sayfa iki yolu çizer: /genel-bakis (CFO kanvası) ve /uyarilar (kural listesi). Planlı raporlar ayrı ekrandır. */


export default function BiCanvasPage() {
  // Ekran yolun son parçasından okunur: /timas/uyarilar → 'uyarilar'.
  const { pathname } = useLocation();
  const screen = pathname.split('/').filter(Boolean).pop();
  // Uyarılar ekranı sekmesini adres taşır: ?panel=yeni → "Yeni kural"; yoksa kural listesi. Geri tuşu sekmeyi geri alır.
  const [params, setParams] = useSearchParams();
  const panel: 'kurallar' | 'yeni' = params.get('panel') === 'yeni' ? 'yeni' : 'kurallar';

  const { alerts } = useCanvasQueries();
  const qc = useQueryClient();
  const cfo = useCfoData();

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
    // Genel bakış CFO ekranıdır; uyarılar yalnız kabuk verisini (kırıntı, ray) kullanır.
    if (screen !== 'uyarilar') return { ...cfoData(cfo, source), zoom: z };
    return { ...alertsData(alert, alerts.isLoading, source), zoom: z };
  }, [screen, cfo, alert, source, zoom, alerts.isLoading]);

  // Soru kutusu başka ürüne gitmez: cevap kanvasın kendi karar kartına düşer.
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [asking, setAsking] = useState(false);
  const [askErr, setAskErr] = useState<string | null>(null);
  /** Cevabı doğuran soru; panoya eklenen kartın başlığı ve yeniden sorulacak sorusu olur. */
  const [answeredQ, setAnsweredQ] = useState('');
  const [board, setBoard] = useState<{ state: BoardAction['state']; message?: string }>({ state: 'idle' });
  // Soru bir modül ekranından geldiyse (?modul=…) o modülün kapsamı: ZEKİ yalnız o modülün konularını cevaplar.
  // Kapsam kaldırılınca (ya da Kampüs'ten gelince) soru konusuna göre ilgili modülün verisine gider.
  const [askModule, setAskModule] = useState<string | null>(null);
  const pages = usePageAccess();
  // Ardışık sorular kuyruğa girer ve tek tek işlenir; yeni soru önceki cevabı ezmez. Her soru sorulduğu kapsamla gider.
  const queueRef = useRef<Array<{ q: string; module: string | null }>>([]);
  const runningRef = useRef(false);
  const [queued, setQueued] = useState(0);
  const [current, setCurrent] = useState<string | null>(null);
  /** Ekranda soru balonunda duran son soru; hata olsa da kalır ki kullanıcı neyin sorulduğunu görsün. */
  const [shownQ, setShownQ] = useState('');
  const runNext = () => {
    const next = queueRef.current.shift();
    setQueued(queueRef.current.length);
    if (next === undefined) {
      runningRef.current = false;
      setAsking(false);
      setCurrent(null);
      return;
    }
    const { q, module } = next;
    runningRef.current = true;
    setAsking(true);
    setCurrent(q);
    setShownQ(q);
    setAskErr(null);
    setAnswer(null);
    setBoard({ state: 'idle' });
    askEngine(q, module)
      .then((a) => {
        setAnsweredQ(q);
        setAnswer({ ...a, summary: a.summary ?? a.explanation });
      })
      .catch((e) => setAskErr(e instanceof EngineAuthError ? 'Oturum gerekli' : 'Zeki AI yanıt vermedi; biraz sonra yeniden sorun'))
      .finally(() => runNext());
  };
  const ask = (q: string, module: string | null = askModule) => {
    if (!ENGINE_ENABLED) return;
    queueRef.current.push({ q, module });
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
  const incomingModule = moduleLabel(params.get('modul')) ? params.get('modul') : null;
  useEffect(() => {
    if (!incoming) return;
    markSplashSeen();
    setSplash(false);
    setParams({}, { replace: true });
    setAskModule(incomingModule);
    ask(incoming, incomingModule);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incoming]);

  const onAsk = (q: string) => ask(q);
  // Modül dışı soruyu tek tıkla ana ZEKİ'ye sormak: kapsam kalkar, soru ilgili modülün verisine gider.
  const askEverywhere = (q: string) => {
    if (runningRef.current || !q.trim()) return;
    setAskModule(null);
    ask(q, null);
  };

  // Yorum çipi: alternatife tıklamak soruyu, belirsiz kelimenin yerine alternatifin ifadesi konmuş hâliyle
  // yeniden sormaktır; yeni uç yok. Bir soru çalışırken gelen ikinci tık (çift tık dahil) yok sayılır:
  // runningRef ilk tıkta eşzamanlı açılır, ekran henüz yenilenmemiş olsa da.
  const interpretChips = useMemo(() => toChips(answer?.interpretations, answeredQ), [answer, answeredQ]);
  const rephrase = (q: string) => {
    if (runningRef.current || !q.trim()) return;
    ask(q);
  };

  // Sohbet cevabı → pano kartı. Doğrusu sunucudaki pano: önce güncel liste okunur (başka sekmede eklenen
  // kart ezilmesin), kart boş yere eklenir, sonra sonucu sunucuda hesaplanır ki pano açılınca hazır olsun.
  const addToBoard = async (): Promise<void> => {
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
    // Gösterilen ve kopyalanan SQL köprünün Logo/CRM'de koşturduğu fiziksel metindir: mantıksal metin (katalog adları,
    // dönem çözülmemiş) SSMS'te aynı sonucu vermez. Panoya kart eklerken mantıksal metin saklanır (yeniden çözülsün).
    const shownSql = answer?.physicalSql || undefined;
    const info = !asking && !askErr && answer?.kaynaklar ? { k: answer.kaynaklar, alan: 'records', label: 'Sorunun cevabı' } : undefined;
    return {
      ...d,
      // Balon sabit örnek soruyu değil sorulan soruyu gösterir; çipten yeniden sorulan metin de burada görünür.
      q: shownQ ? { ...d.q, text: `“${shownQ}”` } : d.q,
      main: {
        ...d.main,
        subject: 'Verine sor',
        // Cevap görünümünde özet motorun ürettiği sorguya dayanır; bekleme/hata anında eski kartın SQL'i gösterilmez.
        sql: !asking && shownSql ? shownSql : undefined,
        info,
        loading: asking,
        model: asking ? `${PHASES[phase]}…` : answer?.latency_ms ? `${(answer.latency_ms / 1000).toFixed(1)} sn` : '',
        text: asking
          ? `“${PHASES[phase]}…”`
          : askErr
            ? `“${askErr}.”`
            : `“${answer?.summary || answer?.explanation ? readableText(answer.summary || answer.explanation || '') : 'Bu soru için gösterilebilir bir cevap bulunamadı.'}”`,
        m1: { label: 'Toplam satır:', value: answer?.records ? String(answer.totalRows ?? answer.rowCount ?? rows) : '—' },
        result: !asking && !askErr && answer?.resultId && !answer.truncated
          ? { id: answer.resultId, totalRows: answer.totalRows ?? answer.rowCount ?? rows } : undefined,
        m2: { label: 'Kolon:', value: answer?.columns ? String(answer.columns.length) : '—' },
        m3: { label: 'Durum:', value: asking ? 'Hesaplanıyor' : answer?.type === 'CLARIFICATION' ? 'Netleştirme gerekiyor' : answer?.type === 'PARTIAL_ANSWER' ? 'Kısmi rapor · eksikler belirtiliyor' : answer?.type === 'TEXT_TO_SQL' ? 'Yanıt hazır' : 'Sonuç alınamadı' },
        note: queued > 0 ? `${queued} soru sırada` : d.main.note,
        board: !asking && answer?.sql && (answer.records?.length ?? 0) > 0 ? { ...board, onAdd: (): void => void addToBoard() } : undefined,
        timing: !asking && answer?.records ? answer : null,
        interpret: !asking && !askErr && interpretChips.length > 0 ? { items: interpretChips, busy: asking, onPick: rephrase } : undefined,
        // Dönem veriden sonra kaldıysa motor aynı soruyu verinin son dönemine kurup gönderir; metin motorundur.
        retry:
          !asking && !askErr && answer?.dataEnd?.suggestion?.question
            ? { question: answer.dataEnd.suggestion.question, busy: asking, onAsk: rephrase }
            : undefined,
        // Modül ekranından gelen soru: hangi modülde sorulduğu ve kapsamı kaldırma (tüm modüllere sor).
        scope: askModule ? { label: moduleLabel(askModule) ?? askModule, busy: asking, onClear: () => setAskModule(null) } : undefined,
        // Konusu dışarıda kalan soru cevaplanmadı: aynı soruyu tek tıkla bütün modüllere sor.
        widen: !asking && !askErr && answer?.type === 'OUT_OF_MODULE' && answeredQ ? { question: answeredQ, busy: asking, onAsk: askEverywhere } : undefined,
        // Cevabın geldiği modül ve (kişi açabiliyorsa) o modülün giriş ekranı.
        origin: !asking && !askErr ? originOf(answer, pages) : undefined,
        // M50: cevabın altında «Doğru / Kısmen / Yanlış»; yalnız soru kaydı olan (motorun cevapladığı) cevapta.
        feedback: !asking && !askErr && answer?.queryId ? { queryId: answer.queryId } : undefined,
        // «Neden?»: ayrıştırılabilir cevapta (katalog ölçüsü + dönem); farkın kanal/cari/kitap katkısı.
        reason: !asking && !askErr && answer?.queryId && answer?.neden?.ok ? { queryId: answer.queryId } : undefined,
      },
      c5: {
        ...d.c5,
        title: 'Üretilen SQL',
        badge: askErr ? 'Hata' : asking ? 'Çalışıyor' : 'Canlı',
        summary: shownSql ?? (asking ? 'Bekleniyor…' : (askErr ?? '')),
        sql: shownSql,
        info,
        latency: answer?.latency_ms ? `${answer.latency_ms} ms` : '—',
        timing: !asking && answer?.records ? answer : null,
      },
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d, answer, asking, askErr, phase, queued, board, answeredQ, shownQ, interpretChips, askModule, pages]);

  if (splash) return <Splash onDone={closeSplash} />;

  // Motor 401 diyorsa veri gelmez; sebebini gizlemeyip giriş kapısını açıyoruz.
  const needsLogin = ENGINE_ENABLED && cfo.authRequired;

  return (
    <>
      {screen === 'uyarilar' ? (
        // Uyarılar: kural listesi ve yeni kural formu sayfanın kendisidir. Önceden burası boş kabuktu ve
        // panele götüren hiçbir düğme yoktu; kural kurma akışına arayüzden ulaşılamıyordu.
        <Shell head={{ tenant: view.tenant, section: view.section, crumb: view.crumb, source: view.source, presence: view.presence }}>
          <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
            <ZoomStage className="h-full">
              <AlertsPanel
                inline
                mode={panel}
                onMode={(m) => setParams(m === 'yeni' ? { panel: m } : {})}
                onClose={() => setParams({})}
                rules={alerts.data?.alerts ?? []}
                email={alerts.data?.email ?? { configured: false, sender: null }}
                draft={null}
                kaynaklar={alerts.data?.kaynaklar}
              />
            </ZoomStage>
          </main>
        </Shell>
      ) : (
        <StitchCanvas d={view} onAsk={onAsk} onZoom={onZoom} zoom={zoom} screen={screen ?? 'genel'} />
      )}
      {needsLogin && <SessionGate onDone={() => qc.invalidateQueries()} />}
    </>
  );
}
