import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpenText, Download, FileText, Link2, Loader2, Sparkles, Trash2, TriangleAlert, CheckCircle2 } from 'lucide-react';
import { Note, Pill, btnGhost, btnPrimary, field, nf } from '../../../admin/ui';
import SqlInfo, { InfoLabel } from '../../../components/SqlInfo';
import { FileDrop } from '../../../components/FileDrop';
import { MB } from '../../../components/fileDropRules';
import { Panel } from '../../kit';
import { ACCEPT_FILES } from '../extract';
import { errMsg, stamp } from '../ui';
import { compareApi, type Clause, type Corpus, type CorpusRow, type DiffRow, type Doc, type Meta, type Op, type PositionResult } from './api';
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
  // Çoklu seçimde dosyalar sırayla yüklenir (her biri arka planda okunur); hata dosya adıyla yazılır.
  const chain = useRef<Promise<void>>(Promise.resolve());
  const [uploading, setUploading] = useState(0);
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);
  const enqueue = (file: File) => {
    setUploading((n) => n + 1);
    chain.current = chain.current.then(() =>
      compareApi.upload(file)
        .then((d) => { setA((x) => x || d.ref); refetch(); })
        .catch((e) => setUploadErrors((xs) => [...xs, `${file.name}: ${errMsg(e)}`]))
        .finally(() => setUploading((n) => n - 1)),
    );
  };
  const remove = useMutation({ mutationFn: compareApi.remove, onSuccess: refetch });
  const unread = items.filter((d) => d.okunabilir !== false && (d.status === 'bekliyor' || d.status === 'hata')).length;
  const canUpload = !!docs.data?.can.upload;
  const canExport = !!docs.data?.can.export;
  const [raw, setRaw] = useState(false);

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
              title="Belge yükle (birden çok)"
              accept={docs.data?.heicVar ? `${ACCEPT_FILES},.heic,.heif` : ACCEPT_FILES}
              maxBytes={10 * MB}
              allowed={canUpload}
              feature="sozlesme-karsilastirma.belge"
              multiple
              busy={uploading > 0}
              onPick={enqueue}
            />
          </div>
        </div>
        {docs.error && <Note tone="err">{errMsg(docs.error)}</Note>}
        {docs.data?.crmHata && <Note tone="warn">{docs.data.crmHata}</Note>}
        {[read.error, readAll.error, remove.error].filter(Boolean).map((e, i) => <Note key={i} tone="err">{errMsg(e)}</Note>)}
        {uploadErrors.map((e) => <Note key={e} tone="err">{e}</Note>)}
        {uploading > 0 && <p className="mt-2 text-[12px] font-semibold text-canvas-violet">{`${uploading} belge yükleniyor…`}</p>}
        <p className="mt-2 text-[11.5px] text-canvas-muted">
          {`Sözleşme numarası dosya adında ya da ilk sayfalarda geçiyorsa belge o sözleşmeye kendiliğinden bağlanır. Metin ekranda kişisel verileri maskelenmiş gösterilir.${docs.data?.saklamaGun ? ` Yüklenen belge ${docs.data.saklamaGun} gün sonra silinir.` : ''}${docs.data && !docs.data.heicVar ? ' Telefon fotoğrafı (HEIC) bu kurulumda okunmuyor; JPEG olarak yükleyin.' : ''}`}
        </p>
        {docs.isLoading && <p className="py-6 text-center text-[12.5px] text-canvas-muted">Arşiv okunuyor…</p>}
        <ul className="mt-3 divide-y divide-slate-100 rounded-2xl border border-slate-100 bg-white/85">
          {items.map((d) => (
            <DocLine
              key={d.ref}
              d={d}
              canLink={canUpload}
              onLinked={refetch}
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
      {ready.length > 0 && canUpload && (
        <label className="flex min-h-11 items-center gap-2 px-1 text-[12.5px] font-bold sm:min-h-0">
          <input type="checkbox" className="h-4 w-4 accent-canvas-violet" checked={raw} onChange={(e) => setRaw(e.target.checked)} />
          Kişisel verileri maskelemeden göster (görüntüleme kayda yazılır)
        </label>
      )}
      {a && b === ALL && <CorpusView a={a} n={ready.length - 1} raw={raw} />}
      {a && b !== ALL && <DiffView a={a} b={b} raw={raw} exportUrl={canExport ? compareApi.diffDocxUrl(a, b) : null} />}
      <p className="px-1 text-[11px] text-canvas-muted">{`Eşleme eşikleri sabittir; emsal ayarları (${meta.ayarlar.emsal} emsal, %${nf.format(meta.ayarlar.esikYuzde)}) yalnız madde değerleri içindir.`}</p>
    </>
  );
}

const docLabel = (d: Doc) => [d.kindLabel, d.contractNo, d.title].filter(Boolean).join(' · ') + (d.maddeSayisi != null ? ` (${d.maddeSayisi} madde)` : '');

function DocLine({ d, canDelete, canLink, onLinked, onRead, onDelete }: {
  d: Doc;
  canDelete: boolean;
  canLink: boolean;
  onLinked: () => void;
  onRead: () => void;
  onDelete: () => void;
}) {
  const [linking, setLinking] = useState(false);
  const [no, setNo] = useState(d.contractNo ?? '');
  const link = useMutation({ mutationFn: () => compareApi.link(d.ref, no.trim()), onSuccess: () => { setLinking(false); onLinked(); } });
  const types = (d.okuma as { turler?: { kural: number; zeki: number; belirsiz: number } } | null)?.turler;
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
        {types && (
          <div className="mt-0.5 text-[11.5px] text-canvas-muted">
            {`Madde türü: ${types.kural} kuralla, ${types.zeki} Zeki AI ile bulundu${types.belirsiz ? `, ${types.belirsiz} belirsiz` : ''}.`}
          </div>
        )}
        {linking && (
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <input className={`${field} w-48`} value={no} placeholder="Sözleşme no" onChange={(e) => setNo(e.target.value)} />
            <button type="button" className={btnPrimary} disabled={link.isPending} onClick={() => link.mutate()}>Bağla</button>
            <button type="button" className={btnGhost} onClick={() => setLinking(false)}>Vazgeç</button>
            {link.error && <span className="text-[11.5px] text-rose-700">{errMsg(link.error)}</span>}
          </div>
        )}
        {d.okuma?.not && <div className="mt-0.5 text-[11.5px] text-amber-800">{d.okuma.not}</div>}
        {d.error && <div className="mt-0.5 text-[11.5px] text-rose-700">{d.error}</div>}
      </div>
      <div className="flex shrink-0 flex-wrap gap-1.5">
        {d.okunabilir !== false && (d.status === 'bekliyor' || d.status === 'hata') && (
          <button type="button" className={btnPrimary} onClick={onRead}>Oku</button>
        )}
        {d.status === 'okunuyor' && <span className="inline-flex items-center gap-1 text-[12px] font-bold text-canvas-violet"><Loader2 aria-hidden className="h-4 w-4 animate-spin" />Okunuyor</span>}
        {canLink && d.kind === 'yukleme' && !linking && (
          <button type="button" className={btnGhost} onClick={() => setLinking(true)}>
            <Link2 aria-hidden className="h-4 w-4" />
            {d.contractNo ? 'Bağı değiştir' : 'Sözleşmeye bağla'}
          </button>
        )}
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

function DiffView({ a, b, raw, exportUrl }: { a: string; b: string; raw: boolean; exportUrl: string | null }) {
  const [only, setOnly] = useState(true);
  const q = useQuery({ queryKey: ['contracts', 'compare', 'diff', a, b, raw], queryFn: () => compareApi.diff(a, b, raw) });
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
        action={exportUrl ? <a className={btnGhost} href={exportUrl}><FileText aria-hidden className="h-4 w-4" />Word raporu</a> : null}
      />
      {d.turler.yalnizB.length > 0 && (
        <p className="mt-2 text-[12px]">
          <span className="font-bold text-rose-700">Karşılaştırılanda olup bu belgede bulunmayan madde türü: </span>
          {d.turler.yalnizB.map((t) => d.turAdlari[t] ?? t).join(', ')}
        </p>
      )}
      <DocPositions list={d.pozisyon} />
      {!rows.length && <p className="py-6 text-center text-[12.5px] text-canvas-muted">Farklı madde yok.</p>}
      <ul className="mt-3 space-y-2">
        {rows.map((r, i) => (
          <li key={i} className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px]">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${TONE[diffTone(r.durum)]}`}>{DIFF_LABEL[r.durum]}</span>
              <span className="font-bold">{clauseTitle(r.a ?? r.b)}</span>
              <TypeChip c={r.a ?? r.b} />
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

function CorpusView({ a, n, raw }: { a: string; n: number; raw: boolean }) {
  const [only, setOnly] = useState(true);
  const q = useQuery({ queryKey: ['contracts', 'compare', 'corpus', a, n, raw], queryFn: () => compareApi.corpus(a, raw), enabled: n > 0 });
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
      {d.eksikTurler.length > 0 && (
        <div className="mt-2 rounded-xl bg-rose-50/70 p-2 text-[12px]">
          <span className="font-bold text-rose-800">Arşivdeki belgelerin çoğunda olup bu belgede olmayan madde türleri: </span>
          {d.eksikTurler.map((t) => `${t.ad} (${t.belge}/${d.belgeSayisi} belgede)`).join(', ')}
        </div>
      )}
      <DocPositions list={d.pozisyon} />
      {!rows.length && <p className="py-6 text-center text-[12.5px] text-canvas-muted">Bütün maddelerin arşivde aynısı var.</p>}
      <ul className="mt-3 space-y-2">
        {rows.map((r, i) => (
          <li key={i} className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px]">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${TONE[corpusTone(r.durum)]}`}>{CORPUS_LABEL[r.durum]}</span>
              <span className="font-bold">{clauseTitle(r.a)}</span>
              <TypeChip c={r.a} />
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

function ResultHead({ title, sub, only, onOnly, chips, info, action }: {
  title: ReactNode;
  sub: string;
  only: boolean;
  onOnly: (v: boolean) => void;
  chips: Array<{ label: string; n: number; tone: keyof typeof TONE }>;
  info: ReactNode;
  action?: ReactNode;
}) {
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[15px] font-extrabold">{title}</h2>
          <p className="mt-0.5 break-words text-[11.5px] text-canvas-muted">{sub}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {action}
          <label className="flex min-h-11 items-center gap-2 text-[12.5px] font-bold sm:min-h-0">
            <input type="checkbox" className="h-4 w-4 accent-canvas-violet" checked={only} onChange={(e) => onOnly(e.target.checked)} />
            Yalnız farklar
          </label>
        </div>
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

/** Maddenin hukuki türü; Zeki AI ile bulunduysa işaretli (kuralla bulunan düz). */
function TypeChip({ c }: { c: Clause | null | undefined }) {
  if (!c?.turAd) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold text-slate-700"
      title={c.turKaynak === 'zeki' ? `Zeki AI ile bulundu (olasılık ${pct(c.olasilik ?? null)})` : 'Madde başlığı ve anahtar sözcüklerle bulundu'}>
      {c.turKaynak === 'zeki' && <Sparkles aria-hidden className="h-3 w-3 text-canvas-violet" />}
      {c.turAd}
    </span>
  );
}

/** Belge madde türü kuralları («belgede fesih maddesi olmalı»): uyan ve aykırı olanlar. */
function DocPositions({ list }: { list: PositionResult[] }) {
  if (!list.length) return null;
  return (
    <ul className="mt-2 space-y-1">
      {list.map((x) => (
        <li key={x.id} className="flex items-start gap-1.5 text-[12px]">
          {x.ok ? <CheckCircle2 aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" /> : <TriangleAlert aria-hidden className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${x.level === 'kirmizi' ? 'text-rose-600' : 'text-amber-600'}`} />}
          <span><span className="font-bold">{x.rule}</span>{` — bu belgede: ${x.value}`}</span>
        </li>
      ))}
    </ul>
  );
}
