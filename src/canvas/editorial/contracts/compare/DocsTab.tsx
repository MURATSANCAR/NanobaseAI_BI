import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpenText, Download, Loader2, Trash2 } from 'lucide-react';
import { Note, Pill, btnGhost, btnPrimary, field, nf } from '../../../admin/ui';
import SqlInfo, { InfoLabel } from '../../../components/SqlInfo';
import { FileDrop } from '../../../components/FileDrop';
import { MB } from '../../../components/fileDropRules';
import { Panel } from '../../kit';
import { ACCEPT_FILES } from '../extract';
import { errMsg, stamp } from '../ui';
import { compareApi, type Corpus, type CorpusRow, type DiffRow, type Doc, type Meta, type Op } from './api';
import { CORPUS_LABEL, DIFF_LABEL, clauseTitle, corpusTone, diffTone, pct, visibleDiff } from './compare';
import { TONE } from './ScanTab';

const ALL = '__arsiv__';

/**
 * Belge metni madde madde: arşiv (CRM ekleri, portal belgeleri, şablonlar, buradan yüklenenler), okuma durumu ve iki
 * belgenin ya da bir belgenin bütün arşive karşı farkı. Şablonun yer tutucusu «doldurulacak alan» sayılır.
 */
export default function DocsTab({ meta }: { meta: Meta }) {
  const qc = useQueryClient();
  const docs = useQuery({
    queryKey: ['contracts', 'compare', 'documents'],
    queryFn: compareApi.documents,
    refetchInterval: (q) => (q.state.data?.items.some((d) => d.status === 'okunuyor') ? 2_000 : false),
  });
  const items = docs.data?.items ?? [];
  const ready = items.filter((d) => d.status === 'hazir');
  const [a, setA] = useState('');
  const [b, setB] = useState(ALL);
  useEffect(() => {
    if (!a && ready[0]) setA(ready[0].ref);
  }, [a, ready]);
  const refetch = () => qc.invalidateQueries({ queryKey: ['contracts', 'compare', 'documents'] });
  const read = useMutation({ mutationFn: compareApi.read, onSuccess: refetch });
  const readAll = useMutation({ mutationFn: compareApi.readAll, onSuccess: () => window.setTimeout(refetch, 800) });
  const upload = useMutation({ mutationFn: compareApi.upload, onSuccess: (d) => { setA(d.ref); refetch(); } });
  const remove = useMutation({ mutationFn: compareApi.remove, onSuccess: refetch });
  const unread = items.filter((d) => d.okunabilir !== false && (d.status === 'bekliyor' || d.status === 'hata')).length;
  const canUpload = !!docs.data?.can.upload;

  return (
    <>
      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="text-[15px] font-extrabold">
              <InfoLabel k={docs.data?.kaynaklar} alan="items[]" label="Belge arşivi">Belge arşivi</InfoLabel>
            </h2>
            <p className="mt-0.5 max-w-[70ch] text-[11.5px] leading-snug text-canvas-muted">
              CRM'de sözleşmeye eklenmiş dosyalar, sözleşme sayfasında okunan belgeler, şablonlar ve buradan yüklenenler. Belge bir kez okunur ve maddelere bölünür; taranmış sayfa da okunur.
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {unread > 0 && (
              <button type="button" className={btnGhost} disabled={readAll.isPending} onClick={() => readAll.mutate()}>
                {readAll.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <BookOpenText aria-hidden className="h-4 w-4" />}
                {`Okunmamış ${nf.format(unread)} belgeyi oku`}
              </button>
            )}
            <FileDrop
              size="button"
              title="Belge yükle"
              accept={ACCEPT_FILES}
              maxBytes={10 * MB}
              allowed={canUpload}
              feature="sozlesme-karsilastirma.belge"
              busy={upload.isPending}
              onPick={(f) => upload.mutate(f)}
            />
          </div>
        </div>
        {docs.error && <Note tone="err">{errMsg(docs.error)}</Note>}
        {docs.data?.crmHata && <Note tone="warn">{docs.data.crmHata}</Note>}
        {[read.error, readAll.error, upload.error, remove.error].filter(Boolean).map((e, i) => <Note key={i} tone="err">{errMsg(e)}</Note>)}
        {docs.isLoading && <p className="py-6 text-center text-[12.5px] text-canvas-muted">Arşiv okunuyor…</p>}
        <ul className="mt-3 divide-y divide-slate-100 rounded-2xl border border-slate-100 bg-white/85">
          {items.map((d) => (
            <DocLine
              key={d.ref}
              d={d}
              canDelete={canUpload}
              onRead={() => read.mutate(d.ref)}
              onDelete={() => {
                if (window.confirm(d.kind === 'yukleme' ? `«${d.title}» silinsin mi? Dosya da silinir.` : `«${d.title}» belgesinin okuması silinsin mi? Belgenin kendisine dokunulmaz.`)) remove.mutate(d.ref);
              }}
            />
          ))}
        </ul>
      </Panel>

      <Panel>
        <h2 className="text-[15px] font-extrabold">Karşılaştır</h2>
        {ready.length === 0 ? (
          <p className="mt-2 text-[12.5px] text-canvas-muted">Karşılaştırmak için önce arşivden en az bir belge okutun ya da belge yükleyin.</p>
        ) : (
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            <label className="block">
              <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">İncelenen belge</span>
              <select className={`${field} mt-1`} value={a} onChange={(e) => { setA(e.target.value); if (e.target.value === b) setB(ALL); }}>
                {ready.map((d) => <option key={d.ref} value={d.ref}>{docLabel(d)}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Neyle karşılaştırılsın</span>
              <select className={`${field} mt-1`} value={b} onChange={(e) => setB(e.target.value)}>
                <option value={ALL}>{`Bütün arşiv (${nf.format(Math.max(0, ready.length - 1))} belge)`}</option>
                {ready.filter((d) => d.ref !== a).map((d) => <option key={d.ref} value={d.ref}>{docLabel(d)}</option>)}
              </select>
            </label>
          </div>
        )}
      </Panel>
      {a && b === ALL && <CorpusView a={a} n={ready.length - 1} />}
      {a && b !== ALL && <DiffView a={a} b={b} />}
      <p className="px-1 text-[11px] text-canvas-muted">{`Eşleme eşikleri sabittir; emsal ayarları (${meta.ayarlar.emsal} emsal, %${nf.format(meta.ayarlar.esikYuzde)}) yalnız madde değerleri içindir.`}</p>
    </>
  );
}

const docLabel = (d: Doc) => [d.kindLabel, d.contractNo, d.title].filter(Boolean).join(' · ') + (d.maddeSayisi != null ? ` (${d.maddeSayisi} madde)` : '');

function DocLine({ d, canDelete, onRead, onDelete }: { d: Doc; canDelete: boolean; onRead: () => void; onDelete: () => void }) {
  const tone = d.okunabilir === false ? 'muted' : d.status === 'hazir' ? 'ok' : d.status === 'hata' ? 'err' : d.status === 'okunuyor' ? 'violet' : 'warn';
  const removable = canDelete && d.status !== 'okunuyor' && (d.kind === 'yukleme' || d.status === 'hazir' || d.status === 'hata');
  return (
    <li className="flex flex-col gap-2 p-3 text-[12.5px] sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone="muted">{d.kindLabel}</Pill>
          <span className="break-all font-bold">{d.title}</span>
          <Pill tone={tone}>{d.statusLabel}</Pill>
        </div>
        <div className="mt-0.5 text-[11.5px] text-canvas-muted">
          {[d.contractNo ? `Sözleşme ${d.contractNo}` : null, d.bytes ? `${nf.format(Math.round(d.bytes / 1024))} KB` : null,
            d.maddeSayisi != null ? `${d.maddeSayisi} madde` : null, d.okuma?.sayfa ? `${d.okuma.sayfa} sayfa` : null,
            d.finishedAt ? `okundu ${stamp(d.finishedAt)}` : null].filter(Boolean).join(' · ')}
        </div>
        {d.okuma?.not && <div className="mt-0.5 text-[11.5px] text-amber-800">{d.okuma.not}</div>}
        {d.error && <div className="mt-0.5 text-[11.5px] text-rose-700">{d.error}</div>}
      </div>
      <div className="flex shrink-0 flex-wrap gap-1.5">
        {d.okunabilir !== false && (d.status === 'bekliyor' || d.status === 'hata') && (
          <button type="button" className={btnPrimary} onClick={onRead}>Oku</button>
        )}
        {d.status === 'okunuyor' && <span className="inline-flex items-center gap-1 text-[12px] font-bold text-canvas-violet"><Loader2 aria-hidden className="h-4 w-4 animate-spin" />Okunuyor</span>}
        {d.kind === 'yukleme' && (
          <a className={btnGhost} href={compareApi.fileUrl(d.ref)} download>
            <Download aria-hidden className="h-4 w-4" />
            İndir
          </a>
        )}
        {removable && (
          <button type="button" className={btnGhost} onClick={onDelete} aria-label={d.kind === 'yukleme' ? 'Belgeyi sil' : 'Okumayı sil'}>
            <Trash2 aria-hidden className="h-4 w-4" />
            {d.kind === 'yukleme' ? 'Sil' : 'Okumayı sil'}
          </button>
        )}
      </div>
    </li>
  );
}

function DiffView({ a, b }: { a: string; b: string }) {
  const [only, setOnly] = useState(true);
  const q = useQuery({ queryKey: ['contracts', 'compare', 'diff', a, b], queryFn: () => compareApi.diff(a, b) });
  const d = q.data;
  const rows = useMemo(() => (d ? visibleDiff(d.maddeler, only) : []), [d, only]);
  if (q.error) return <Note tone="err">{errMsg(q.error)}</Note>;
  if (!d) return <Panel><p className="py-8 text-center text-[12.5px] text-canvas-muted">Maddeler eşleniyor…</p></Panel>;
  return (
    <Panel>
      <ResultHead
        title={<InfoLabel k={d.kaynaklar} alan="maddeler[]" label="Madde madde fark">Madde madde fark</InfoLabel>}
        sub={`${d.a.title} ↔ ${d.b.title}`}
        only={only}
        onOnly={setOnly}
        chips={(Object.keys(DIFF_LABEL) as DiffRow['durum'][]).map((k) => ({ label: DIFF_LABEL[k], n: d.sayim[k], tone: diffTone(k) }))}
        info={<SqlInfo k={d.kaynaklar} alan="sayim" label="Madde sayıları" />}
      />
      {!rows.length && <p className="py-6 text-center text-[12.5px] text-canvas-muted">Farklı madde yok.</p>}
      <ul className="mt-3 space-y-2">
        {rows.map((r, i) => (
          <li key={i} className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px]">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${TONE[diffTone(r.durum)]}`}>{DIFF_LABEL[r.durum]}</span>
              <span className="font-bold">{clauseTitle(r.a ?? r.b)}</span>
              {r.a && r.b && clauseTitle(r.a) !== clauseTitle(r.b) && <span className="text-[11.5px] text-canvas-muted">{`↔ ${clauseTitle(r.b)}`}</span>}
              {r.a && r.b && <span className="text-[11px] text-canvas-muted">{`benzerlik ${pct(r.benzerlik)}`}</span>}
            </div>
            {r.sayilar && (
              <p className="mt-1 text-[11.5px] font-semibold text-rose-700">{`Sayılar farklı — karşılaştırılanda: ${r.sayilar.b.join(', ') || 'yok'} · bu belgede: ${r.sayilar.a.join(', ') || 'yok'}`}</p>
            )}
            <div className="mt-1.5 leading-relaxed">
              {r.fark ? <DiffText ops={r.fark} /> : <p className="whitespace-pre-wrap break-words">{(r.a ?? r.b)?.metin}</p>}
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function CorpusView({ a, n }: { a: string; n: number }) {
  const [only, setOnly] = useState(true);
  const q = useQuery({ queryKey: ['contracts', 'compare', 'corpus', a, n], queryFn: () => compareApi.corpus(a), enabled: n > 0 });
  const d: Corpus | undefined = q.data;
  const rows = useMemo(() => (d ? visibleDiff(d.maddeler, only) : []), [d, only]);
  if (n <= 0) return <Panel><p className="py-6 text-center text-[12.5px] text-canvas-muted">Arşivde karşılaştırılacak başka okunmuş belge yok.</p></Panel>;
  if (q.error) return <Note tone="err">{errMsg(q.error)}</Note>;
  if (!d) return <Panel><p className="py-8 text-center text-[12.5px] text-canvas-muted">Her madde arşivde aranıyor…</p></Panel>;
  return (
    <Panel>
      <ResultHead
        title={<InfoLabel k={d.kaynaklar} alan="maddeler[]" label="Arşive karşı">Arşive karşı</InfoLabel>}
        sub={`${d.a.title} · ${nf.format(d.belgeSayisi)} belgeyle`}
        only={only}
        onOnly={setOnly}
        chips={(Object.keys(CORPUS_LABEL) as CorpusRow['durum'][]).map((k) => ({ label: CORPUS_LABEL[k], n: d.sayim[k], tone: corpusTone(k) }))}
        info={<SqlInfo k={d.kaynaklar} alan="sayim" label="Madde sayıları" />}
      />
      {!rows.length && <p className="py-6 text-center text-[12.5px] text-canvas-muted">Bütün maddelerin arşivde aynısı var.</p>}
      <ul className="mt-3 space-y-2">
        {rows.map((r, i) => (
          <li key={i} className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px]">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${TONE[corpusTone(r.durum)]}`}>{CORPUS_LABEL[r.durum]}</span>
              <span className="font-bold">{clauseTitle(r.a)}</span>
              {r.benzerBelge > 0 && <span className="text-[11px] text-canvas-muted">{`${r.benzerBelge} belgede benzeri`}</span>}
            </div>
            {r.enYakin && (
              <p className="mt-1 text-[11.5px] text-canvas-muted">
                {`En yakın: ${[r.enYakin.belge.kindLabel, r.enYakin.belge.contractNo, r.enYakin.belge.title].filter(Boolean).join(' · ')} — ${clauseTitle(r.enYakin.madde)} (benzerlik ${pct(r.enYakin.benzerlik)})`}
              </p>
            )}
            <div className="mt-1.5 leading-relaxed">
              {r.fark ? <DiffText ops={r.fark} /> : <p className="whitespace-pre-wrap break-words">{r.a.metin}</p>}
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function ResultHead({ title, sub, only, onOnly, chips, info }: {
  title: ReactNode;
  sub: string;
  only: boolean;
  onOnly: (v: boolean) => void;
  chips: Array<{ label: string; n: number; tone: keyof typeof TONE }>;
  info: ReactNode;
}) {
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[15px] font-extrabold">{title}</h2>
          <p className="mt-0.5 break-words text-[11.5px] text-canvas-muted">{sub}</p>
        </div>
        <label className="flex min-h-11 items-center gap-2 text-[12.5px] font-bold sm:min-h-0">
          <input type="checkbox" className="h-4 w-4 accent-canvas-violet" checked={only} onChange={(e) => onOnly(e.target.checked)} />
          Yalnız farklar
        </label>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {chips.map((c) => (
          <span key={c.label} className={`inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-[11.5px] font-bold ${TONE[c.tone]}`}>
            {c.label}
            <span className="font-mono tabular-nums">{nf.format(c.n)}</span>
          </span>
        ))}
        {info}
      </div>
      <p className="mt-2 text-[11px] text-canvas-muted">
        <span className="rounded bg-emerald-100 px-1 text-emerald-900">yeşil</span> yalnız incelenen belgede,{' '}
        <span className="rounded bg-rose-100 px-1 text-rose-900 line-through">kırmızı</span> yalnız karşılaştırılanda,{' '}
        <span className="rounded bg-violet-100 px-1 text-violet-900">mor</span> şablon alanının doldurulduğu yer.
      </p>
    </>
  );
}

/** Kelime farkı: eklenen yeşil, çıkan kırmızı üstü çizili, şablon alanı mor (yer tutucunun adı ipucunda). */
export function DiffText({ ops }: { ops: Op[] }) {
  return (
    <p className="whitespace-pre-wrap break-words">
      {ops.map((o, i) => {
        const sp = i < ops.length - 1 ? ' ' : '';
        if (o.op === 'eq') return <span key={i}>{o.text + sp}</span>;
        if (o.op === 'ins') return <span key={i}><ins className="rounded bg-emerald-100 px-0.5 text-emerald-900 no-underline">{o.text}</ins>{sp}</span>;
        if (o.op === 'del') return <span key={i}><del className="rounded bg-rose-100 px-0.5 text-rose-900">{o.text}</del>{sp}</span>;
        return (
          <span key={i}>
            <mark className="rounded bg-violet-100 px-0.5 text-violet-900" title={`Şablon alanı: ${o.alan ?? ''}`}>{o.text || '—'}</mark>
            {sp}
          </span>
        );
      })}
    </p>
  );
}
