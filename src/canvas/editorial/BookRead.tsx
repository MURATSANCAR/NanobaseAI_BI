import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, X } from 'lucide-react';
import { ENGINE_ENABLED, EngineAuthError, bookReadApi, type BookRead } from '../engine';
import { Note, Pill, field, label, nf } from '../admin/ui';
import { dateTime } from '../format';
import { FileDrop } from '../components/FileDrop';
import { fmtSize } from '../components/fileDropRules';
import { ShowMoreButton, useShowMore } from '../components/ShowMore';
import { Panel } from './kit';

/** Kitap okut (Kitaba sor'un üstü): editör bir ya da birçok PDF bırakır. Dosyalar tarayıcıdan sırayla yüklenir
 *  (kopan bağlantı kendiliğinden yeniden denenir), köprünün giden kutusuna alınır, oradan okuma kuyruğuna geçer;
 *  ZEKİ AI aynı anda tek kitap okur, düşen okumayı kendisi yeniden dener. Her kitabın durumu satırında yazar:
 *  Yükleniyor → Gönderiliyor → Sırada (önünde n kitap) → Okunuyor (aşama) → Kitaba sor'da. Kalıcı olan tek
 *  sorun dosyanın kendisidir (PDF değil, bozuk, parolalı); o da satırda sade cümleyle yazar. */

type Tone = 'ok' | 'warn' | 'err' | 'muted' | 'violet';

/** Tarayıcıdaki yükleme sırası: sayfa açıkken dosya elde tutulur, gönderilene kadar yeniden denenir. */
type Local = {
  key: string;
  file: File;
  title: string;
  state: 'bekliyor' | 'yukleniyor' | 'baglanti' | 'reddedildi';
  share: number;
  tries: number;
  nextAt: number;
  message?: string;
};

const RETRY = [5_000, 15_000, 30_000, 60_000];
/** Yeniden denenebilir: bağlantı yok (0), zaman aşımı, çok istek, sunucu/kapı hatası. 4xx'in geri kalanı kalıcıdır. */
const transient = (status: number) => status === 0 || status === 408 || status === 429 || status >= 500;
const moving = (b: BookRead) => b.state === 'gonderiliyor' || b.state === 'sirada' || b.state === 'okunuyor' || b.state === 'yeniden';
/** Okuması bitti ama soru listesine henüz girmedi: köprü listeyi arkada tazeler, ekran kısa aralıkla yeniden sorar. */
const joining = (b: BookRead) => b.state === 'hazir' && !b.listed;

function serverState(b: BookRead): { tone: Tone; text: string; note?: string } {
  switch (b.state) {
    case 'gonderiliyor':
      return b.waiting
        ? { tone: 'muted', text: 'Bağlantı bekleniyor', note: 'ZEKİ AI şu an ulaşılamıyor; dosya sunucuda güvende, bağlantı gelince kendiliğinden gönderilir.' }
        : { tone: 'muted', text: 'Gönderiliyor' };
    case 'sirada':
      return { tone: 'muted', text: 'Sırada', note: b.ahead ? `Önünde ${nf.format(b.ahead)} kitap var; sırası gelince okuma kendiliğinden başlar.` : 'Sıradaki kitap bu; birazdan okunmaya başlar.' };
    case 'okunuyor':
      return { tone: 'violet', text: 'Okunuyor' };
    case 'yeniden':
      return { tone: 'warn', text: 'Yeniden deneniyor', note: `Okuma yarıda kaldı; ZEKİ AI kitabı yeniden sıraya aldı (${b.attempt + 1}. deneme / ${b.attempts}).` };
    case 'okunamadi':
      return { tone: 'err', text: 'Okunamadı', note: b.message || (b.attempts > 1 ? `${b.attempts} denemede okunamadı; dosyayı kontrol edip yeniden yükleyin.` : 'Dosya okunamadı; dosyayı kontrol edip yeniden yükleyin.') };
    default:
      return b.listed ? { tone: 'ok', text: "Kitaba sor'da" } : { tone: 'ok', text: 'Listeye ekleniyor' };
  }
}

function Bar({ share, label: aria }: { share: number; label: string }) {
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-label={aria} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(share * 100)}>
      {/* Genişlik değil ölçek: yalnız transform canlanır. */}
      <div
        className="h-full w-full origin-left rounded-full bg-gradient-to-r from-canvas-coral to-canvas-violet transition-transform duration-300 ease-out motion-reduce:transition-none"
        style={{ transform: `scaleX(${Math.max(0.04, Math.min(1, share))})` }}
      />
    </div>
  );
}

function Shell({ title, pill, children, onClose }: { title: string; pill: { tone: Tone; text: string }; children?: ReactNode; onClose?: () => void }) {
  return (
    <li className="rounded-xl border border-slate-100 bg-white/85 px-2.5 py-2 text-[12px]">
      <span className="flex items-center gap-1.5">
        <BookOpen aria-hidden className="h-3.5 w-3.5 shrink-0 text-canvas-muted" />
        <span className="min-w-0 flex-1 truncate font-bold">{title}</span>
        <Pill tone={pill.tone}>{pill.text}</Pill>
        {onClose && (
          <button type="button" onClick={onClose} aria-label={`${title} satırını kaldır`} className="zk-press -m-1 rounded-md p-1 text-canvas-muted hover:text-canvas-ink">
            <X aria-hidden className="h-3.5 w-3.5" />
          </button>
        )}
      </span>
      {children}
    </li>
  );
}

function LocalRow({ l, onClose }: { l: Local; onClose: () => void }) {
  const pill: { tone: Tone; text: string } =
    l.state === 'yukleniyor'
      ? { tone: 'violet', text: `Yükleniyor %${Math.round(l.share * 100)}` }
      : l.state === 'baglanti'
        ? { tone: 'muted', text: 'Bağlantı bekleniyor' }
        : l.state === 'reddedildi'
          ? { tone: 'err', text: 'Yüklenemedi' }
          : { tone: 'muted', text: 'Yükleme sırasında' };
  return (
    <Shell title={l.title || l.file.name} pill={pill} onClose={l.state === 'reddedildi' ? onClose : undefined}>
      {l.state === 'yukleniyor' && (
        <div className="mt-1.5">
          <Bar share={l.share} label={`${l.file.name} yükleniyor`} />
        </div>
      )}
      <span className="mt-0.5 block text-[11px] text-canvas-muted">
        {fmtSize(l.file.size)}
        {l.state === 'baglanti' ? ' · Bağlantı kopunca yükleme kendiliğinden yeniden denenir; bu sekmeyi kapatmayın.' : ''}
        {l.state === 'reddedildi' && l.message ? ` · ${l.message}` : ''}
      </span>
    </Shell>
  );
}

function ServerRow({ b, onClose }: { b: BookRead; onClose?: () => void }) {
  const st = serverState(b);
  return (
    <Shell title={b.title} pill={st} onClose={onClose}>
      {b.state === 'okunuyor' && (
        <div className="mt-1.5">
          <Bar share={b.phase.n / (b.phase.of || 1)} label={`${b.title} okuma ilerlemesi`} />
          <span className="mt-1 block text-[11px] text-canvas-muted">
            {b.phase.label} · adım {b.phase.n}/{b.phase.of}
            {b.attempt > 1 ? ` · ${b.attempt}. deneme` : ''}
          </span>
        </div>
      )}
      {st.note && <span className="mt-1 block text-[11px] leading-snug text-canvas-muted">{st.note}</span>}
      <span className="mt-0.5 block truncate text-[11px] text-canvas-muted">
        {b.pages ? `${nf.format(b.pages)} sayfa · ` : ''}
        {b.finished_at ? `bitti ${dateTime(b.finished_at)}` : `gönderildi ${dateTime(b.created_at)}`}
        {b.requested_by ? ` · ${b.requested_by}` : ''}
      </span>
    </Shell>
  );
}

export default function BookReadPanel() {
  const qc = useQueryClient();
  const [title, setTitle] = useState('');
  const [local, setLocal] = useState<Local[]>([]);
  const [tick, setTick] = useState(0);
  const list = useQuery({
    queryKey: ['editorial', 'bookReads'],
    queryFn: bookReadApi.list,
    enabled: ENGINE_ENABLED,
    // Gönderim/sıra/okuma sürerken durum kendiliğinden ilerler; biten kitap listeye girene kadar daha sık bakılır.
    refetchInterval: (q) => {
      const xs = q.state.data?.items ?? [];
      if (q.state.data?.stale || xs.some((b) => b.state === 'gonderiliyor' || joining(b))) return 10_000;
      return xs.some(moving) ? 30_000 : false;
    },
  });
  const items = list.data?.items ?? [];

  // Tarayıcı sırası: aynı anda tek dosya yüklenir (sunucuyu ve bağlantıyı boğmaz); kopan yükleme beklenip yeniden denenir.
  const running = useRef(false);
  useEffect(() => {
    if (running.current) return;
    const now = Date.now();
    const next = local.find((l) => (l.state === 'bekliyor' || l.state === 'baglanti') && l.nextAt <= now);
    if (!next) {
      const wait = local.filter((l) => l.state === 'baglanti').map((l) => l.nextAt - now);
      if (!wait.length) return;
      const t = window.setTimeout(() => setTick((n) => n + 1), Math.max(500, Math.min(...wait)));
      return () => window.clearTimeout(t);
    }
    running.current = true;
    const set = (patch: Partial<Local>) => setLocal((xs) => xs.map((l) => (l.key === next.key ? { ...l, ...patch } : l)));
    set({ state: 'yukleniyor', share: 0 });
    bookReadApi
      .upload(next.file, next.title, (share) => set({ share }))
      .then(async () => {
        setLocal((xs) => xs.filter((l) => l.key !== next.key));
        await qc.invalidateQueries({ queryKey: ['editorial', 'bookReads'] });
      })
      .catch((e: unknown) => {
        const status = e instanceof EngineAuthError ? 401 : ((e as { status?: number }).status ?? 0);
        const message = e instanceof EngineAuthError ? 'Oturum kapanmış; sayfayı yenileyip yeniden girin.' : e instanceof Error ? e.message : undefined;
        if (transient(status)) set({ state: 'baglanti', tries: next.tries + 1, nextAt: Date.now() + RETRY[Math.min(next.tries, RETRY.length - 1)] });
        else set({ state: 'reddedildi', message });
      })
      .finally(() => {
        running.current = false;
        setTick((n) => n + 1);
      });
  }, [local, tick, qc]);

  // Yüklenmemiş dosya varken sekme kapatılırsa tarayıcı uyarır (dosya henüz sunucuda değil).
  const unsent = local.some((l) => l.state !== 'reddedildi');
  useEffect(() => {
    if (!unsent) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [unsent]);

  // Bir kitap Kitaba sor listesine girince sohbetin kitap listesi de tazelenir.
  const listed = items.filter((b) => b.listed).map((b) => b.id).join(',');
  const seen = useRef(listed);
  useEffect(() => {
    if (listed === seen.current) return;
    seen.current = listed;
    void qc.invalidateQueries({ queryKey: ['editorial', 'readableBooks'] });
  }, [listed, qc]);

  const pick = (file: File) =>
    setLocal((xs) => {
      const one = xs.length === 0 && title.trim();
      return [...xs, { key: `${file.name}-${file.size}-${file.lastModified}-${Math.random()}`, file, title: one ? title.trim() : '', state: 'bekliyor', share: 0, tries: 0, nextAt: 0 }];
    });

  const dismiss = async (id: string) => {
    try {
      await bookReadApi.dismiss(id);
    } finally {
      await qc.invalidateQueries({ queryKey: ['editorial', 'bookReads'] });
    }
  };

  const more = useShowMore(items, 5);
  const counts = {
    sirada: items.filter((b) => b.state === 'sirada' || b.state === 'gonderiliyor').length + local.filter((l) => l.state !== 'reddedildi').length,
    okunuyor: items.filter((b) => b.state === 'okunuyor' || b.state === 'yeniden').length,
  };
  return (
    <Panel>
      <div className="space-y-2.5">
        <FileDrop
          accept=".pdf"
          size="sm"
          multiple
          feature="kitap.okut"
          title="Kitap okut"
          hint="Bir ya da birçok kitabın PDF'ini bırakın. ZEKİ AI kitapları sırayla okur: sayfalar, resimler, karakterler ve olaylar. Biten kitap Kitaba sor'a girer. Okuma uzun sürebilir; yükleme bitince bu sayfadan ayrılabilirsiniz."
          onPick={pick}
        />
        <details className="rounded-2xl border border-slate-100 bg-white/70 px-3 py-2">
          <summary className="cursor-pointer select-none text-[12px] font-bold text-canvas-ink">İsteğe bağlı: kitabın adı</summary>
          <label className="mt-2 block">
            <span className={label}>Kitabın adı (tek dosya yüklerken)</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Boşsa dosya adından" className={`${field} mt-1`} />
          </label>
        </details>
        {list.data?.stale && <Note tone="info">ZEKİ AI'a şu an ulaşılamıyor; son bilinen durum gösteriliyor, bağlantı gelince kendiliğinden güncellenir.</Note>}
        {(local.length > 0 || items.length > 0) && (
          <div>
            <h3 className="flex items-baseline gap-2 px-1 text-[12px] font-extrabold">
              Okutulan kitaplar
              {(counts.okunuyor > 0 || counts.sirada > 0) && (
                <span className="text-[11px] font-semibold text-canvas-muted">
                  {counts.okunuyor > 0 ? `${nf.format(counts.okunuyor)} okunuyor` : ''}
                  {counts.okunuyor > 0 && counts.sirada > 0 ? ' · ' : ''}
                  {counts.sirada > 0 ? `${nf.format(counts.sirada)} sırada` : ''}
                </span>
              )}
            </h3>
            <ul className="mt-1.5 space-y-1" aria-label="Okutulan kitaplar">
              {local.map((l) => (
                <LocalRow key={l.key} l={l} onClose={() => setLocal((xs) => xs.filter((x) => x.key !== l.key))} />
              ))}
              {more.shown.map((b) => (
                <ServerRow key={b.id} b={b} onClose={b.state === 'okunamadi' && b.id.startsWith('gonder-') ? () => void dismiss(b.id) : undefined} />
              ))}
            </ul>
            <ShowMoreButton more={more} noun="kitap" />
          </div>
        )}
      </div>
    </Panel>
  );
}
