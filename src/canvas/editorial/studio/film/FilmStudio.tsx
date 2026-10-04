import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  AlertTriangle, BadgeCheck, CircleDashed, Clapperboard, FileText, Image as ImageIcon, Loader2, Mic, Plus, Scissors,
  Share2, Sparkles, Users, Video,
} from 'lucide-react';
import { Loading, Note, errText } from '../../../admin/ui';
import { Panel } from '../../kit';
import { Progress, ago, ghostBtn, gradientBtn, press } from '../shared';
import { Explain } from '../../../components/Explain';
import { useCan } from '../../../useAdmin';
import {
  filmApi, isBusy, useFilm, useFilmRefresh, useFilms,
  type FilmFormat, type FilmMeta, type FilmStyle, type FilmView, type Stage, type StageKey,
} from './api';
import { StageBody } from './FilmStages';

/** Stüdyonun «Film ve video» bölümü: kitaptan çizgi film, kitap fragmanı ya da sosyal medya kısa videosu. Yedi adım
 *  sırayla yürür (senaryo → oyuncular → ses → ilk kareler → çekim → kurgu → paylaşım); Zeki AI üretir, editör beş
 *  noktada onaylar. Adım değişimi anlıktır (sık kullanılır, hareket yok); basışta stüdyonun `press` küçülmesi. */

const STAGES: [StageKey, string, typeof FileText][] = [
  ['senaryo', 'Senaryo', FileText], ['oyuncular', 'Oyuncular', Users], ['ses', 'Ses', Mic],
  ['kareler', 'İlk kareler', ImageIcon], ['cekim', 'Çekim', Video], ['kurgu', 'Kurgu', Scissors],
  ['paylasim', 'Paylaşım', Share2],
];
export const NEEDS_APPROVAL: StageKey[] = ['senaryo', 'oyuncular', 'kareler', 'kurgu', 'paylasim'];
const NEEDS: Record<StageKey, StageKey[]> = {
  senaryo: [], oyuncular: ['senaryo'], ses: ['oyuncular'], kareler: ['oyuncular'], cekim: ['ses', 'kareler'],
  kurgu: ['cekim'], paylasim: ['kurgu'],
};
const START_TEXT: Record<StageKey, [string, string]> = {
  senaryo: ['Senaryoyu yaz', 'Senaryoyu yeniden yaz'], oyuncular: ['Oyuncuları hazırla', 'Oyuncuları yeniden hazırla'],
  ses: ['Replikleri seslendir', 'Yeniden seslendir'], kareler: ['İlk kareleri çiz', 'Eksik kareleri çiz'],
  cekim: ['Çekimleri yap', 'Eksik çekimleri yap'], kurgu: ['Kurguyu yap', 'Kurguyu yeniden yap'],
  paylasim: ['Paylaşım paketini hazırla', 'Paketi yeniden hazırla'],
};
const FORMAT_NOTE: Record<FilmFormat, string> = {
  'cizgi-film': 'Yatay, 1–10 dakika. Kitabın hikâyesi sahne sahne.',
  fragman: 'Yatay, 45–120 saniye. Merak uyandıran kitap tanıtımı.',
  reels: 'Dikey, 15–90 saniye. Instagram, TikTok, Shorts; altyazı görüntüde.',
};

function ready(m: FilmMeta, k: StageKey): boolean {
  const s = m.stages[k]?.status;
  return NEEDS_APPROVAL.includes(k) ? s === 'onayli' : s === 'hazir' || s === 'onayli';
}

function StatusChip({ k, s }: { k: StageKey; s: Stage | undefined }) {
  const st = s?.status ?? 'bekliyor';
  const map: Record<string, [string, string]> = {
    bekliyor: ['Bekliyor', 'bg-slate-100 text-canvas-muted'], sirada: ['Sırada', 'bg-sky-50 text-sky-700'],
    calisiyor: ['Çalışıyor', 'bg-sky-50 text-sky-700'],
    hazir: [NEEDS_APPROVAL.includes(k) ? 'Onay bekliyor' : 'Hazır', NEEDS_APPROVAL.includes(k) ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'],
    onayli: ['Onaylı', 'bg-emerald-50 text-emerald-700'], eski: ['Güncel değil', 'bg-amber-50 text-amber-700'],
    hata: ['Hata', 'bg-rose-50 text-rose-700'], sorunlu: ['Düzeltme gerek', 'bg-rose-50 text-rose-700'],
  };
  const [t, cls] = map[st] ?? map.bekliyor;
  return <span className={`rounded-full px-2 py-0.5 text-[10.5px] font-bold ${cls}`}>{t}</span>;
}

function NewFilm({ jobId, formats, styles, onMade }: {
  jobId: string; formats: Record<FilmFormat, { label: string }>; styles: Record<FilmStyle, string>; onMade: (id: string) => void;
}) {
  const [format, setFormat] = useState<FilmFormat>('reels');
  const [style, setStyle] = useState<FilmStyle>('2b');
  const make = useMutation({ mutationFn: () => filmApi.create(jobId, { format, style }), onSuccess: (m) => onMade(m.id) });
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white/70 p-3">
      <div role="radiogroup" aria-label="Biçim" className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {(Object.keys(formats) as FilmFormat[]).map((f) => (
          <button key={f} type="button" role="radio" aria-checked={format === f} onClick={() => setFormat(f)}
            className={`flex min-h-16 flex-col items-start gap-0.5 rounded-xl border-2 px-3 py-2 text-left ${press} ${format === f ? 'border-canvas-violet bg-violet-50' : 'border-slate-200 bg-white'}`}>
            <span className="text-[13px] font-extrabold">{formats[f].label}</span>
            <span className="text-[11.5px] leading-snug text-canvas-muted">{FORMAT_NOTE[f]}</span>
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex min-w-[12rem] flex-1 flex-col gap-1">
          <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Görsel üslup</span>
          <select value={style} onChange={(e) => setStyle(e.target.value as FilmStyle)}
            className="min-h-10 rounded-xl border border-slate-200 bg-white px-3 text-[13px] outline-none focus:border-canvas-violet">
            {(Object.keys(styles) as FilmStyle[]).map((s) => <option key={s} value={s}>{styles[s]}</option>)}
          </select>
        </label>
        <button type="button" className={gradientBtn} disabled={make.isPending} onClick={() => make.mutate()}>
          {make.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Plus className="h-4 w-4" aria-hidden />}
          Filmi aç
        </button>
      </div>
      {make.error && <Note tone="err">{errText(make.error, 'Film açılamadı.')}</Note>}
    </div>
  );
}

function StageBar({ jobId, v, k, refresh }: { jobId: string; v: FilmView; k: StageKey; refresh: () => void }) {
  const m = v.film;
  const s = m.stages[k] ?? { status: 'bekliyor' };
  const canProduce = useCan('tasarim.uret');
  const [platforms, setPlatforms] = useState<string[]>(['instagram-reels', 'tiktok', 'youtube-shorts']);
  const start = useMutation({ mutationFn: () => filmApi.start(jobId, m.id, k, k === 'paylasim' ? { platforms } : {}),
    onSettled: refresh });
  const approve = useMutation({ mutationFn: (ok: boolean) => filmApi.approve(jobId, m.id, k, ok), onSettled: refresh });
  const blocked = NEEDS[k].filter((n) => !ready(m, n));
  const running = s.status === 'sirada' || s.status === 'calisiyor' || start.isPending;
  const has = !['bekliyor', 'hata'].includes(s.status);
  const [n, t] = s.progress ?? [0, 0];
  const label = STAGES.find(([x]) => x === blocked[0])?.[1];
  return (
    <div className="flex flex-col gap-2">
      {k === 'paylasim' && !running && <PlatformPick value={platforms} onChange={setPlatforms} />}
      <div className="flex flex-wrap items-center gap-2">
        {(canProduce || running) && (
          <button type="button" className={has ? ghostBtn : gradientBtn} disabled={running || !canProduce || blocked.length > 0
            || (k === 'paylasim' && !platforms.length)} onClick={() => start.mutate()}>
            {running ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Sparkles className="h-4 w-4" aria-hidden />}
            {running ? (s.status === 'sirada' ? 'Sırada…' : 'Zeki AI çalışıyor…') : START_TEXT[k][has ? 1 : 0]}
          </button>
        )}
        {NEEDS_APPROVAL.includes(k) && (s.status === 'hazir' || s.status === 'onayli') && canProduce && (
          <button type="button" disabled={approve.isPending} onClick={() => approve.mutate(s.status !== 'onayli')}
            className={`inline-flex min-h-10 items-center gap-2 rounded-xl border-2 px-4 text-[13px] font-bold ${press} ${s.status === 'onayli' ? 'border-slate-200 bg-white text-canvas-muted' : 'border-emerald-500 bg-white text-emerald-700'}`}>
            <BadgeCheck className="h-4 w-4" aria-hidden />{s.status === 'onayli' ? 'Onayı geri al' : 'Onayla'}
          </button>
        )}
        {s.status === 'onayli' && s.approved_by && s.approved_at && (
          <span className="text-[11.5px] text-canvas-muted">Onaylayan {s.approved_by} · {ago(s.approved_at)}</span>
        )}
        {running && s.step && <span className="text-[12px] text-canvas-muted">{s.step}{t ? ` · ${n}/${t}` : ''}</span>}
      </div>
      {blocked.length > 0 && !running && (
        <p className="flex items-center gap-1.5 text-[12px] text-canvas-muted"><CircleDashed className="h-3.5 w-3.5" aria-hidden />
          Önce «{label}» adımı {NEEDS_APPROVAL.includes(blocked[0]) ? 'onaylanmalı' : 'bitmeli'}.</p>
      )}
      {running && t > 0 && <Progress value={n} total={t} />}
      {running && <p className="text-[11.5px] text-canvas-muted">Bu adım arka planda sürer; sayfadan ayrılabilirsiniz, bitince sonuç burada olur.</p>}
      {s.status === 'eski' && <Note tone="warn">Önceki bir adım değişti; bu adımın sonucu güncel değil. Yeniden çalıştırın.</Note>}
      {(start.error || s.status === 'hata') && (
        <p className="flex items-start gap-1.5 text-[12px] text-rose-700"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          {start.error ? errText(start.error, 'Adım başlatılamadı.') : s.error || 'Adım tamamlanamadı.'}</p>
      )}
      {!!s.failed_qc && <Note tone="warn">{s.failed_qc} sonuç otomatik denetimden geçmedi; aşağıda işaretli. Yeniden üretin ya da kontrol ederek onaylayın.</Note>}
    </div>
  );
}

const PLATFORM_LABEL: Record<string, string> = {
  'instagram-reels': 'Instagram Reels', tiktok: 'TikTok', 'youtube-shorts': 'YouTube Shorts', youtube: 'YouTube',
  'instagram-kare': 'Instagram kare',
};

function PlatformPick({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  return (
    <fieldset className="flex flex-wrap gap-1.5">
      <legend className="mb-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Platformlar</legend>
      {Object.entries(PLATFORM_LABEL).map(([k, t]) => {
        const on = value.includes(k);
        return (
          <label key={k} className={`inline-flex min-h-10 cursor-pointer items-center gap-2 rounded-xl border px-3 text-[12.5px] font-bold ${press} ${on ? 'border-canvas-violet bg-violet-50 text-canvas-violet' : 'border-slate-200 bg-white'}`}>
            <input type="checkbox" className="h-4 w-4 accent-violet-600" checked={on}
              onChange={() => onChange(on ? value.filter((x) => x !== k) : [...value, k])} />{t}
          </label>
        );
      })}
    </fieldset>
  );
}

function FilmPane({ jobId, fid }: { jobId: string; fid: string }) {
  const q = useFilm(jobId, fid);
  const refresh = useFilmRefresh(jobId);
  const [stage, setStage] = useState<StageKey>('senaryo');
  const v = q.data;
  useEffect(() => {
    // Açılışta ilk bitmemiş adım seçili gelir.
    if (!v) return;
    const first = STAGES.find(([k]) => !ready(v.film, k));
    if (first) setStage(first[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fid, !!v]);
  if (!v) return q.error ? <Note tone="info">{errText(q.error, 'Film okunamadı.')}</Note> : <Loading />;
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div role="tablist" aria-label="Film adımları" className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
        {STAGES.map(([k, t, Icon], i) => (
          <button key={k} type="button" role="tab" id={`film-tab-${k}`} aria-selected={stage === k} aria-controls={`film-panel-${k}`}
            onClick={() => setStage(k)}
            className={`flex min-h-14 shrink-0 flex-col items-start justify-center gap-1 rounded-xl border px-3 py-1.5 text-left ${press} ${stage === k ? 'border-canvas-violet bg-violet-50' : 'border-slate-200 bg-white/70'}`}>
            <span className="inline-flex items-center gap-1.5 text-[12.5px] font-bold">
              <span className="text-[10.5px] font-extrabold text-canvas-muted">{i + 1}</span>
              <Icon className="h-4 w-4" aria-hidden />{t}
            </span>
            <StatusChip k={k} s={v.film.stages[k]} />
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`film-panel-${stage}`} aria-labelledby={`film-tab-${stage}`} className="flex min-w-0 flex-col gap-3">
        <StageBar jobId={jobId} v={v} k={stage} refresh={refresh} />
        <StageBody jobId={jobId} v={v} k={stage} refresh={refresh} />
      </div>
    </div>
  );
}

export default function FilmStudio({ jobId }: { jobId: string }) {
  const q = useFilms(jobId);
  const refresh = useFilmRefresh(jobId);
  const [fid, setFid] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const list = q.data;
  const films = list?.films ?? [];
  const current = fid ?? films[0]?.id ?? null;
  const canProduce = useCan('tasarim.uret');
  return (
    <Panel>
      <div id="film" className="flex min-w-0 flex-col gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-[16px] font-extrabold">
            <Clapperboard className="h-5 w-5 text-canvas-violet" aria-hidden />Film ve video
            <Explain label="Film ve video" className="-ml-1">Kitaptan çizgi film, kitap fragmanı ya da sosyal medya kısa videosu. Zeki AI senaryoyu kitaptan yazar, karakterleri karakter kartına göre çizer, replikleri seçtiğiniz seslerle okur, çekimleri yapar ve kurgular. Senaryo, oyuncular, ilk kareler, kurgu ve paylaşım paketi sizin onayınızı bekler. Hiçbir şey kendiliğinden paylaşılmaz; onaylı dosyaları indirip siz paylaşırsınız.</Explain>
          </h2>
          <p className="text-[12px] text-canvas-muted">Senaryodan paylaşıma yedi adım. Zeki AI üretir, siz düzeltip onaylarsınız.</p>
        </div>
        {!list ? (q.error ? <Note tone="info">{errText(q.error, 'Filmler okunamadı.')}</Note> : <Loading />) : (
          <>
            <div className="-mx-1 flex flex-wrap gap-1.5 px-1">
              {films.map((f) => (
                <button key={f.id} type="button" onClick={() => { setFid(f.id); setAdding(false); }} aria-pressed={current === f.id && !adding}
                  className={`inline-flex min-h-10 items-center gap-2 rounded-xl border px-3 text-[12.5px] font-bold ${press} ${current === f.id && !adding ? 'border-canvas-violet bg-violet-50 text-canvas-violet' : 'border-slate-200 bg-white/70'}`}>
                  {list.formats[f.format]?.label ?? f.format} · {list.styles[f.style] ?? f.style}
                  {isBusy(f) && <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-label="çalışıyor" />}
                </button>
              ))}
              {canProduce && (
                <button type="button" onClick={() => setAdding(true)} aria-pressed={adding} className={ghostBtn}>
                  <Plus className="h-4 w-4" aria-hidden />Yeni film
                </button>
              )}
            </div>
            {(adding || (!films.length && canProduce)) ? (
              <NewFilm jobId={jobId} formats={list.formats} styles={list.styles}
                onMade={(id) => { setFid(id); setAdding(false); refresh(); }} />
            ) : current ? <FilmPane key={current} jobId={jobId} fid={current} />
              : <Note tone="info">Bu kitap için henüz film yok.</Note>}
          </>
        )}
      </div>
    </Panel>
  );
}
