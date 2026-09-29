import { useId } from 'react';
import { Link } from 'react-router-dom';
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { Pill, field, label, nf } from '../../admin/ui';
import { applicationsApi, type AppStatus, type Tally } from './api';
import { Explain } from '../../components/Explain';

/** M1 ekranlarının ortak parçaları: durum rozeti, puan alanı, oy dağılımı, sorgu anahtarları. */

export const STATUS_TONE: Record<AppStatus, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  yeni: 'violet',
  degerlendirmede: 'warn',
  revizyon: 'warn',
  kurul_bekliyor: 'violet',
  kurulda: 'violet',
  kabul: 'ok',
  red: 'err',
  geri_cekildi: 'muted',
};

export function StatusPill({ status, label: text }: { status: AppStatus; label: string }) {
  return <Pill tone={STATUS_TONE[status] ?? 'muted'}>{text}</Pill>;
}

export const DECISION_TONE: Record<string, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  kabul: 'ok',
  revizyon: 'warn',
  red: 'err',
  ertele: 'muted',
  ertelendi: 'muted',
  cekimser: 'muted',
};

export const appMetaOptions = () =>
  queryOptions({ queryKey: ['applications', 'meta'], queryFn: applicationsApi.meta, enabled: ENGINE_ENABLED, staleTime: 5 * 60_000 });

export function useAppMeta() {
  return useQuery(appMetaOptions());
}

export function useCategories(enabled = true) {
  return useQuery({
    queryKey: ['applications', 'categories'],
    queryFn: applicationsApi.categories,
    enabled: ENGINE_ENABLED && enabled,
    staleTime: 30 * 60_000,
  });
}

/** Başvuru ya da kurul kaydı değişince ilişkili bütün görünümler yeniden okunur. */
export function invalidateApps(qc: QueryClient): Promise<void> {
  return qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === 'applications' || q.queryKey[0] === 'board' });
}

export const errMsg = (e: unknown, fallback = 'Kaydedilemedi.') => (e instanceof Error && e.message ? e.message : fallback);

/** 0–100 puan: dokunmatikte kaydırıcı, klavyede sayı. Boş bırakılabilir (henüz puanlanmadı). */
export function ScoreField({
  title,
  hint,
  value,
  onChange,
  disabled,
}: {
  title: string;
  hint?: string;
  value: number | null;
  onChange: (v: number | null) => void;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor={id} className={label}>
          {title}
        </label>
        <input
          type="number"
          inputMode="numeric"
          min={0}
          max={100}
          aria-label={`${title} (0–100)`}
          value={value ?? ''}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value === '' ? null : Math.max(0, Math.min(100, Math.round(Number(e.target.value)))))}
          className={`${field} !w-20 text-right font-mono tabular-nums`}
        />
      </div>
      <input
        id={id}
        type="range"
        min={0}
        max={100}
        step={1}
        value={value ?? 50}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className={`mt-1 h-8 w-full accent-[theme(colors.canvas.violet)] ${value == null ? 'opacity-40' : ''}`}
      />
      {hint && <p className="text-[11px] leading-snug text-canvas-muted">{hint}</p>}
    </div>
  );
}

export const AXES: Array<{ key: 'mission' | 'publishing' | 'commercial'; title: string; hint: string }> = [
  { key: 'mission', title: 'Misyon değeri', hint: 'Yayınevinin çizgisine ve okura katkısına uygunluk' },
  { key: 'publishing', title: 'Yayıncılık değeri', hint: 'Metnin niteliği, özgünlüğü, yazarın yetkinliği' },
  { key: 'commercial', title: 'Ticari değer', hint: 'Satış potansiyeli, pazar ve kanal uygunluğu' },
];

/** Oy dağılımı ve ortalamalar; gizliyse yalnız kaç üyenin oy verdiği. */
export function TallyView({ tally, compact }: { tally: Tally; compact?: boolean }) {
  if (tally.hidden || !tally.counts) {
    return (
      <p className="text-[12px] text-canvas-muted">
        {nf.format(tally.voted)} / {nf.format(tally.members)} üye oy verdi. Dağılım, oyunuzu verince görünür.
      </p>
    );
  }
  const c = tally.counts;
  const total = Math.max(1, tally.voted);
  const bars: Array<{ k: keyof typeof c; label: string; cls: string }> = [
    { k: 'kabul', label: 'Kabul', cls: 'bg-emerald-500' },
    { k: 'revizyon', label: 'Revizyon', cls: 'bg-amber-400' },
    { k: 'red', label: 'Red', cls: 'bg-rose-500' },
    { k: 'cekimser', label: 'Çekimser', cls: 'bg-slate-300' },
  ];
  return (
    <div className="space-y-2 text-[12px]">
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-slate-100" role="img" aria-label={bars.map((b) => `${b.label} ${c[b.k]}`).join(', ')}>
        {bars.map((b) => (c[b.k] > 0 ? <span key={b.k} className={b.cls} style={{ width: `${(c[b.k] / total) * 100}%` }} /> : null))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {bars.map((b) => (
          <span key={b.k} className="inline-flex items-center gap-1">
            <span aria-hidden className={`h-2 w-2 rounded-full ${b.cls}`} />
            {b.label} <b className="font-mono tabular-nums">{nf.format(c[b.k])}</b>
          </span>
        ))}
        <span className="text-canvas-muted">
          · {nf.format(tally.voted)} / {nf.format(tally.members)} üye
        </span>
      </div>
      {!compact && (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 sm:grid-cols-4">
          <Stat k="Misyon" v={tally.axes?.mission} />
          <Stat k="Yayıncılık" v={tally.axes?.publishing} />
          <Stat k="Ticari" v={tally.axes?.commercial} />
          <Stat k="Toplam skor" v={tally.total} strong />
        </dl>
      )}
      <p className="text-[12px] leading-snug">
        <span className="text-canvas-muted">Oy çoğunluğu: </span>
        <b>{tally.majorityLabel ?? (tally.tie ? 'eşit — karar başkanda' : 'yok')}</b>
        <span className="text-canvas-muted"> · Skor önerisi: </span>
        <b>{tally.byScoreLabel ?? '—'}</b>
        {tally.thresholds && (
          <span className="text-canvas-muted">
            {' '}
            (kabul ≥ {tally.thresholds.accept}, revizyon ≥ {tally.thresholds.revise})
          </span>
        )}{' '}
        <Explain label="Oy çoğunluğu ve skor önerisi">
          Oy çoğunluğu en çok oyu alan seçenektir. Toplam skor, üç eksen ortalamasının ortalamasıdır; eşiği geçerse kabul ya da revizyon, geçmezse red önerilir. İkisi de yalnız yol gösterir, kararı başkan verir.
        </Explain>
      </p>
    </div>
  );
}

function Stat({ k, v, strong }: { k: string; v: number | null | undefined; strong?: boolean }) {
  return (
    <div>
      <dt className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{k}</dt>
      <dd className={`font-mono tabular-nums ${strong ? 'text-[16px] font-extrabold' : 'text-[13px] font-bold'}`}>{v == null ? '—' : String(v).replace('.', ',')}</dd>
    </div>
  );
}

/** Bayt → «1,2 MB». */
export function fmtBytes(n: number): string {
  if (n < 1024) return `${nf.format(n)} B`;
  if (n < 1024 * 1024) return `${nf.format(Math.round(n / 1024))} KB`;
  return `${(n / 1024 / 1024).toFixed(1).replace('.', ',')} MB`;
}

export const ACTION_TEXT: Record<string, string> = {
  olusturuldu: 'Başvuru kaydedildi',
  formdan: 'Yazar başvuru formundan alındı',
  duzenlendi: 'Bilgiler düzenlendi',
  dosya: 'Dosya yüklendi',
  dosya_silindi: 'Dosya silindi',
  atandi: 'Editör atandı',
  rapor_tamamlandi: 'Editör raporu tamamlandı',
  karar_kurula: 'Yayın kuruluna çıkarıldı',
  karar_revizyon: 'Yazardan revizyon istendi',
  karar_red: 'Reddedildi ve arşive alındı',
  karar_geri_cekildi: 'Yazar geri çekti',
  yeniden_acildi: 'Yeniden açıldı',
  gundeme_alindi: 'Kurul gündemine alındı',
  gundemden_cikti: 'Kurul gündeminden çıkarıldı',
  oy: 'Kurul üyesi oy verdi',
  kurul_kabul: 'Kurul: kabul',
  kurul_revizyon: 'Kurul: revizyon',
  kurul_red: 'Kurul: red',
  kurul_ertele: 'Kurul: sonraki kurula ertelendi',
  kurul_ertelendi: 'Kurul oturumu kararsız kapandı; ertelendi',
  kurul_karari_geri: 'Kurul kararı geri alındı',
  yazi_hazirlandi: 'Yazı taslağı hazırlandı',
  yazi_onaylandi: 'Yazı onaylandı',
  yazi_onayi_geri: 'Yazının onayı geri alındı',
  yazi_gonderildi: 'Yazı gönderildi',
  yazi_silindi: 'Yazı taslağı silindi',
  crm_baglandi: 'CRM proje kartı bağlandı',
  crm_bag_kaldirildi: 'CRM proje bağı kaldırıldı',
};

/** Yayın kurulu sayfasının iki görünümü: portal oturumları ve CRM'deki geçmiş kararlar. */
export function BoardTabs({ active }: { active: 'oturum' | 'crm' }) {
  const cls = (on: boolean) =>
    `flex min-h-11 items-center justify-center rounded-xl px-2 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${on ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'}`;
  return (
    <nav className="grid grid-cols-2 gap-1 rounded-2xl bg-slate-100 p-1" aria-label="Yayın kurulu görünümü">
      <Link to="/yayin-kurulu" className={cls(active === 'oturum')} aria-current={active === 'oturum' ? 'page' : undefined}>
        Kurul oturumları
      </Link>
      <Link to="/yayin-kurulu?gorunum=crm" className={cls(active === 'crm')} aria-current={active === 'crm' ? 'page' : undefined}>
        Geçmiş kararlar (CRM)
      </Link>
    </nav>
  );
}
