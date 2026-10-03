import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, Loader2, Plus, RotateCcw, Scissors, Search, Trash2 } from 'lucide-react';
import { Note, errText } from '../../../admin/ui';
import { Explain } from '../../../components/Explain';
import { ghostBtn, press } from '../shared';
import { EpubError, epubApi, type DuzenBlock, type DuzenChapter, type DuzenOp, type DuzenView } from './api';

/** E-kitap düzeni: yayınevinin e-kitap şablonunda bölümler (ad, bölme, öncekine katma), paragraf stili (epigraf, şiir,
 *  alıntı, ara işareti, ara başlık, gizle), ön sayfalar (imza, künye, yazar tanıtımı) ve basılı kitapta olup e-kitapta
 *  olmayan parçaları e-kitaba ekleme. Düzen basılı kitaba dokunmaz; bir sonraki e-kitap üretiminde uygulanır. */

const field = 'rounded-xl border border-slate-200 bg-white/90 px-3 text-base outline-none focus:border-canvas-violet sm:text-[12.5px]';

function pagesText(p: [number, number]) {
  return p[0] === p[1] ? `s. ${p[0]}` : `s. ${p[0]}–${p[1]}`;
}

function TitleInput({ value, label, onSave, disabled }: { value: string; label: string; onSave: (t: string) => void; disabled: boolean }) {
  const [t, setT] = useState(value);
  useEffect(() => setT(value), [value]);
  const commit = () => {
    const v = t.trim();
    if (v && v !== value) onSave(v);
    else setT(value);
  };
  return (
    <input aria-label={label} value={t} disabled={disabled} maxLength={160} onChange={(e) => setT(e.target.value)}
      onBlur={commit} onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); if (e.key === 'Escape') setT(value); }}
      className={`${field} min-h-9 min-w-0 flex-1 font-extrabold`} />
  );
}

function BlockRow({ b, styles, busy, run }: { b: DuzenBlock; styles: Record<string, string>; busy: boolean; run: (ops: DuzenOp[]) => void }) {
  const [splitting, setSplitting] = useState(false);
  const [title, setTitle] = useState('');
  const hidden = b.style === 'gizle';
  return (
    <li className={`grid gap-1.5 rounded-xl px-2.5 py-2 text-[12px] sm:grid-cols-[1fr_190px] ${hidden ? 'bg-slate-100/80 text-canvas-muted line-through' : 'bg-white/70'}`}>
      <p className="line-clamp-3 leading-snug">{b.text}{b.long ? '…' : ''}</p>
      <div className="flex flex-col gap-1">
        <select value={b.style ?? ''} disabled={busy} aria-label="Paragrafın e-kitap stili"
          onChange={(e) => run([{ op: 'style', block: b.id, style: e.target.value }])} className={`${field} min-h-9`}>
          <option value="">Otomatik ({styles[b.auto] ?? 'Paragraf'})</option>
          {Object.entries(styles).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        {!splitting && !b.split && (
          <button type="button" className={`self-start rounded-lg px-1.5 py-1 text-[11.5px] font-bold text-canvas-violet hover:bg-violet-50 ${press}`}
            disabled={busy} onClick={() => setSplitting(true)}>
            <Scissors className="mr-1 inline h-3.5 w-3.5" aria-hidden />Buradan yeni bölüm
          </button>
        )}
      </div>
      {splitting && (
        <form className="flex flex-wrap items-center gap-1.5 sm:col-span-2" onSubmit={(e) => {
          e.preventDefault();
          if (!title.trim()) return;
          run([{ op: 'split', block: b.id, title: title.trim(), on: true }]);
          setSplitting(false);
        }}>
          <input autoFocus aria-label="Yeni bölümün adı" placeholder="Yeni bölümün adı" value={title} maxLength={160}
            onChange={(e) => setTitle(e.target.value)} className={`${field} min-h-9 min-w-0 flex-1`} />
          <button type="submit" className={ghostBtn} disabled={busy || !title.trim()}>Böl</button>
          <button type="button" className={ghostBtn} onClick={() => setSplitting(false)}>Vazgeç</button>
        </form>
      )}
    </li>
  );
}

function ChapterRow({ ch, index, open, toggle, styles, busy, run, query }: {
  ch: DuzenChapter; index: number; open: boolean; toggle: () => void; styles: Record<string, string>; busy: boolean;
  run: (ops: DuzenOp[]) => void; query: string;
}) {
  const custom = ch.blocks.filter((b) => b.style).length;
  const blocks = query ? ch.blocks.filter((b) => b.text.toLocaleLowerCase('tr').includes(query)) : ch.blocks;
  if (query && !blocks.length) return null;
  const shown = open || !!query;
  return (
    <li className={`rounded-2xl border p-2 ${ch.merged ? 'border-dashed border-slate-300 bg-slate-50/70' : 'border-slate-200 bg-white/60'}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <button type="button" aria-expanded={shown} aria-label={shown ? 'Paragrafları gizle' : 'Paragrafları göster'}
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg hover:bg-slate-100 ${press}`} onClick={toggle}>
          {shown ? <ChevronDown className="h-4 w-4" aria-hidden /> : <ChevronRight className="h-4 w-4" aria-hidden />}
        </button>
        <TitleInput value={ch.title} label={`${index + 1}. bölümün adı`} disabled={busy}
          onSave={(t) => run([{ op: 'title', chapter: ch.key, title: t }])} />
        <span className="shrink-0 text-[11px] font-semibold text-canvas-muted">
          {ch.blocks.length} paragraf{custom ? ` · ${custom} stil seçili` : ''}
        </span>
        {ch.split && (
          <button type="button" className={ghostBtn} disabled={busy} onClick={() => run([{ op: 'split', block: ch.key, on: false }])}>
            Bölmeyi kaldır
          </button>
        )}
        {index > 0 && (
          <label className="flex min-h-9 shrink-0 cursor-pointer items-center gap-1.5 rounded-lg px-2 text-[11.5px] font-bold">
            <input type="checkbox" checked={ch.merged} disabled={busy} className="h-4 w-4 accent-canvas-violet"
              onChange={(e) => run([{ op: 'merge', chapter: ch.key, on: e.target.checked }])} />
            Öncekine kat
          </label>
        )}
      </div>
      {ch.merged && <p className="mt-1 px-2 text-[11.5px] text-canvas-muted">Bu bölüm öncekinin devamı olur; adı metin içinde ara başlık olarak kalır, yeni sayfa açılmaz.</p>}
      {shown && (
        <ul className="mt-2 flex flex-col gap-1">
          {blocks.map((b) => <BlockRow key={b.id} b={b} styles={styles} busy={busy} run={run} />)}
        </ul>
      )}
    </li>
  );
}

function MissingRow({ m, busy, run }: { m: DuzenView['missing'][number]; busy: boolean; run: (ops: DuzenOp[]) => void }) {
  const [title, setTitle] = useState('');
  return (
    <li className="flex flex-col gap-1.5 rounded-xl bg-white/70 px-2.5 py-2 text-[12px]">
      <div>
        <span className="font-bold">{pagesText(m.pages)}</span>
        <span className="text-canvas-muted"> · {m.words.toLocaleString('tr-TR')} kelime{m.reason ? ` · ${m.reason}` : ''}</span>
        <span className="mt-0.5 block text-[11.5px] leading-snug text-canvas-muted">«{m.text}…»</span>
      </div>
      {m.added ? <span className="text-[11.5px] font-bold text-emerald-700">E-kitaba eklendi (kitabın sonunda)</span> : (
        <form className="flex flex-wrap items-center gap-1.5" onSubmit={(e) => {
          e.preventDefault();
          if (title.trim()) run([{ op: 'add_missing', pages: m.pages, title: title.trim() }]);
        }}>
          <input aria-label="Eklenecek bölümün adı" placeholder="Bölüm adı (ör. Yazarın Notu)" value={title} maxLength={160}
            onChange={(e) => setTitle(e.target.value)} className={`${field} min-h-9 min-w-0 flex-1`} />
          <button type="submit" className={ghostBtn} disabled={busy || !title.trim()}><Plus className="h-4 w-4" aria-hidden />E-kitaba ekle</button>
        </form>
      )}
    </li>
  );
}

export default function EpubEditor({ jobId }: { jobId: string }) {
  const qc = useQueryClient();
  const key = ['studio', 'epub', jobId, 'duzen'];
  const q = useQuery({ queryKey: key, queryFn: () => epubApi.duzen(jobId), enabled: !!jobId });
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const [search, setSearch] = useState('');
  const query = search.trim().toLocaleLowerCase('tr');
  const [stale, setStale] = useState(false);
  const save = useMutation({
    mutationFn: (ops: DuzenOp[]) => epubApi.setDuzen(jobId, q.data?.rev ?? 0, ops),
    onSuccess: (data) => {
      setStale(false);
      qc.setQueryData(key, data);
      void qc.invalidateQueries({ queryKey: ['studio', 'epub', jobId], exact: true });
    },
    onError: (e) => {
      if (e instanceof EpubError && e.status === 409) {
        setStale(true);
        void q.refetch();
      }
    },
  });
  const v = q.data;
  const busy = save.isPending;
  const run = (ops: DuzenOp[]) => save.mutate(ops);
  const changed = useMemo(() => v ? v.chapters.some((c) => c.merged || c.split || c.renamed || c.blocks.some((b) => b.style))
    || v.extras.length > 0 || v.fronts.some((f) => !f.on) : false, [v]);

  if (q.isLoading) return <p className="flex items-center gap-2 text-[12px] text-canvas-muted"><Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />E-kitap düzeni okunuyor…</p>;
  if (q.error || !v) return <Note tone="err">{errText(q.error, 'E-kitap düzeni okunamadı.')}</Note>;
  if (!v.house) return <Note tone="warn">Düzenleme yayınevinin e-kitap şablonuyla üretilen akışkan e-kitapta yapılır.</Note>;

  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-white/50 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-1 text-[13px] font-extrabold">
          E-kitap düzeni
          <Explain label="E-kitap düzeni">Bölüm adlarını, bölünmeyi ve paragrafların e-kitaptaki stilini (epigraf, şiir, alıntı…) yalnız e-kitap için değiştirir; basılı kitap değişmez. Değişiklikler kaydedilir ve e-kitap yeniden üretilince dosyaya girer.</Explain>
        </h3>
        <div className="flex items-center gap-2">
          {busy && <Loader2 className="h-4 w-4 animate-spin text-canvas-muted motion-reduce:animate-none" aria-label="Kaydediliyor" />}
          {changed && (
            <button type="button" className={ghostBtn} disabled={busy}
              onClick={() => { if (window.confirm('E-kitap düzenindeki bütün değişiklikler silinsin mi?')) run([{ op: 'reset' }]); }}>
              <RotateCcw className="h-4 w-4" aria-hidden />Düzeni sıfırla
            </button>
          )}
        </div>
      </div>
      {stale && <Note tone="warn">Düzen başka bir yerde değişti; ekran yenilendi, son işleminizi yeniden yapın.</Note>}
      {save.error && !stale && <Note tone="err">{errText(save.error, 'Kaydedilemedi.')}</Note>}
      {v.warnings.map((w) => <Note key={w} tone="warn">{w}</Note>)}

      <fieldset className="flex flex-wrap gap-2">
        <legend className="mb-1 text-[12px] font-extrabold">Ön sayfalar</legend>
        {v.fronts.map((f) => (
          <label key={f.key} className="flex min-h-9 cursor-pointer items-center gap-1.5 rounded-xl border border-slate-200 bg-white/80 px-2.5 text-[12px] font-bold">
            <input type="checkbox" checked={f.on} disabled={busy} className="h-4 w-4 accent-canvas-violet"
              onChange={(e) => run([{ op: 'front', key: f.key, on: e.target.checked }])} />
            {f.label}
          </label>
        ))}
      </fieldset>

      {(v.missing.length > 0 || v.extras.length > 0) && (
        <section className="flex flex-col gap-1.5">
          <h4 className="text-[12px] font-extrabold">Basılıda olup e-kitapta olmayan</h4>
          {v.missing.length > 0 && <ul className="flex flex-col gap-1">{v.missing.map((m) => <MissingRow key={`${m.pages[0]}-${m.pages[1]}`} m={m} busy={busy} run={run} />)}</ul>}
          {v.extras.length > 0 && (
            <ul className="flex flex-col gap-1">
              {v.extras.map((x) => (
                <li key={x.id} className="flex flex-wrap items-center gap-2 rounded-xl bg-emerald-50/70 px-2.5 py-1.5 text-[12px]">
                  <span className="min-w-0 flex-1"><b>{x.title}</b> <span className="text-canvas-muted">· basılı {pagesText(x.pages)} · {x.words.toLocaleString('tr-TR')} kelime · kitabın sonunda</span></span>
                  <button type="button" className={ghostBtn} disabled={busy} onClick={() => run([{ op: 'remove_extra', id: x.id }])}>
                    <Trash2 className="h-4 w-4" aria-hidden />Çıkar
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-[12px] font-extrabold">Bölümler ve paragraflar <span className="font-bold text-canvas-muted">· {v.chapters.length} bölüm</span></h4>
          <label className="relative flex w-full min-w-0 items-center sm:w-auto">
            <Search className="pointer-events-none absolute left-2.5 h-4 w-4 text-canvas-muted" aria-hidden />
            <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Paragraf ara"
              aria-label="Paragraflarda ara" className={`${field} min-h-9 w-full pl-8 sm:w-56`} />
          </label>
        </div>
        <ul className="flex flex-col gap-1.5">
          {v.chapters.map((ch, i) => (
            <ChapterRow key={ch.key} ch={ch} index={i} styles={v.styles} busy={busy} run={run} query={query}
              open={open.has(ch.key)} toggle={() => setOpen((s) => {
                const n = new Set(s);
                if (n.has(ch.key)) n.delete(ch.key); else n.add(ch.key);
                return n;
              })} />
          ))}
        </ul>
      </section>
    </div>
  );
}
