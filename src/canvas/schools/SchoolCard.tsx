import { useState, type ReactNode } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { CalendarPlus, ClipboardPen, FileDown, Phone, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { downloadCatalog, schoolsApi, type Catalog, type SchoolDetail } from './api';
import { CalendarNote, SchoolsFrame, ScoreBadge, ScoreParts, addDays, daysAgo, fmtDay, fmtMoney, fmtNum, invalidateSchools, useSchoolsMeta } from './parts';
import VisitReportSheet from './VisitReportSheet';
import DealerPanel from './DealerPanel';
import SqlInfo from '../components/SqlInfo';
import { ShowMoreButton, useShowMore } from '../components/ShowMore';

/** Okul kartı (telefon öncelikli): profil, öncelik ve gerekçesi, Zeki AI ziyaret önerisi, bağlı/önerilen bayi, kademeye
 *  uygun katalog + PDF, geçmiş ziyaretler (portal + CRM), okul siparişleri. Listenin kaynağı ve tarihi görünür. */

function Block({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{title}</h2>
        {action}
      </div>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function Fact({ label, value, info }: { label: string; value: string; info?: ReactNode }) {
  return (
    <div className="rounded-xl bg-white/85 px-3 py-2">
      <div className="flex items-center gap-0.5 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">
        {label}
        {info}
      </div>
      <div className="mt-0.5 font-mono text-[15px] font-bold tabular-nums">{value}</div>
    </div>
  );
}

export default function SchoolCard() {
  const { id = '' } = useParams();
  const meta = useSchoolsMeta();
  const me = meta.data?.me;
  const today = meta.data?.today ?? new Date().toISOString().slice(0, 10);
  const card = useQuery({ queryKey: ['schools', 'card', id], queryFn: () => schoolsApi.card(id), enabled: ENGINE_ENABLED && !!id });
  const [report, setReport] = useState(false);
  const [planOpen, setPlanOpen] = useState(false);
  const c = card.data;
  const s = c?.school;

  return (
    <SchoolsFrame
      back
      title={s?.name ?? 'Okul'}
      lead={s ? [s.ilce ? `${s.ilce}, ${s.il ?? ''}` : s.il, s.kademe ?? s.gradesText, s.kurumTuru, s.okulTuru].filter(Boolean).join(' · ') : undefined}
      source={c ? `${c.source.label} · okundu ${fmtDay(c.source.asOf)}` : 'CRM + Logo'}
      presence={c ? `Kayıt son değişiklik ${fmtDay(c.source.changed)}` : 'Okul kartı'}
    >
      {card.error && <Note tone="err">{errText(card.error, 'Okul kartı okunamadı.')}</Note>}
      {card.isLoading && <Loading />}
      {c && s && (
        <>
          {c.warnings.map((w) => (
            <Note key={w} tone="warn">
              {w}
            </Note>
          ))}
          <CalendarNote hits={c.calendar} />
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <Fact label="Öğrenci" value={s.students != null ? fmtNum(s.students) : 'bilinmiyor'} info={<SqlInfo k={c.kaynaklar} alan="school" label="Öğrenci sayısı" />} />
            <Fact label="Öğretmen" value={s.teachers != null ? fmtNum(s.teachers) : '—'} info={<SqlInfo k={c.kaynaklar} alan="school" label="Öğretmen sayısı" />} />
            <Fact label="Derslik" value={s.classrooms != null ? fmtNum(s.classrooms) : '—'} info={<SqlInfo k={c.kaynaklar} alan="school" label="Derslik sayısı" />} />
            <Fact label="Kütüphane kitabı" value={s.libraryBooks != null ? fmtNum(s.libraryBooks) : '—'} info={<SqlInfo k={c.kaynaklar} alan="school" label="Kütüphane kitabı" />} />
            <Fact label="Son ziyaret" value={daysAgo(c.lastVisit, today)} info={<SqlInfo k={c.kaynaklar} alan="parts" label="Son ziyaret (CRM + portal)" />} />
            <Fact label="Uygun, stokta kitap" value={c.logoOk ? fmtNum(c.fittingBooks) : 'stok okunamadı'} info={<SqlInfo k={c.kaynaklar} alan="fittingBooks" label="Uygun, stokta kitap" />} />
          </div>
          {s.phone && (
            <a href={`tel:${s.phone.replace(/[^\d+]/g, '')}`} className={`${btnGhost} self-start`}>
              <Phone aria-hidden className="h-4 w-4" />
              {s.phone}
            </a>
          )}

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <Block
              title="Öncelik"
              action={
                <span className="flex items-center gap-1">
                  <SqlInfo k={c.kaynaklar} alan="score" label="Öncelik puanı" />
                  <ScoreBadge score={c.score} />
                </span>
              }
            >
              <p className="mb-2 text-[12.5px] leading-snug">{c.reason}</p>
              <details>
                <summary className="min-h-11 cursor-pointer text-[12px] font-bold text-canvas-violet sm:min-h-0">Puan nasıl hesaplandı</summary>
                <div className="mt-2">
                  <ScoreParts parts={c.parts} />
                </div>
              </details>
            </Block>
            <Advice id={s.id} />
          </div>

          {planOpen && <AddPlan id={s.id} today={today} onDone={() => setPlanOpen(false)} />}

          <DealerPanel schoolId={s.id} canDealer={!!me?.canDealer} canVisit={!!me?.canVisit} />
          <CatalogPanel detail={c} canVisit={!!me?.canVisit} canExport={!!me?.canExport} />
          <Visits c={c} />
          <Orders c={c} />
          <p className="px-1 text-[11px] leading-snug text-canvas-muted">
            Okul bilgileri CRM ziyaret yerleri listesinden ({fmtDay(c.source.asOf)} okundu; bu kaydın CRM'deki son değişikliği {fmtDay(c.source.changed)}).
            Öğrenci sayısı CRM'de metin alanıdır; sayıya çevrilemeyen değer «bilinmiyor» gösterilir.
          </p>

          {/* Telefon: en sık işlemler başparmak erimde; kaydırılan alanın altına yapışık (menü çubuğunun üstünde kalır). */}
          <div className="sticky bottom-0 z-30 flex gap-2 rounded-2xl border border-slate-100 bg-white/95 p-2 shadow-glass-float lg:static lg:self-start lg:border-0 lg:bg-transparent lg:p-0 lg:shadow-none">
            {me?.canVisit && (
              <button type="button" className={`${btnPrimary} flex-1 lg:flex-none`} onClick={() => setReport(true)}>
                <ClipboardPen aria-hidden className="h-4 w-4" />
                Ziyaret raporu gir
              </button>
            )}
            {me?.canVisit && (
              <button type="button" className={`${btnGhost} flex-1 lg:flex-none`} onClick={() => setPlanOpen((x) => !x)} aria-expanded={planOpen}>
                <CalendarPlus aria-hidden className="h-4 w-4" />
                Plana ekle
              </button>
            )}
          </div>
          {report && <VisitReportSheet open schoolId={s.id} schoolName={s.name} onClose={() => setReport(false)} />}
        </>
      )}
    </SchoolsFrame>
  );
}

function Advice({ id }: { id: string }) {
  const run = useMutation({ mutationFn: () => schoolsApi.advice(id) });
  return (
    <Block
      title="Zeki AI ziyaret önerisi"
      action={
        <button type="button" className={btnGhost} onClick={() => run.mutate()} disabled={run.isPending}>
          <Sparkles aria-hidden className="h-4 w-4" />
          {run.isPending ? 'Yazıyor…' : run.data ? 'Yeniden yaz' : 'Öneri al'}
        </button>
      }
    >
      {run.error && <Note tone="err">{errText(run.error, 'Öneri alınamadı.')}</Note>}
      {run.data ? (
        <>
          <p className="text-[13px] leading-relaxed">{run.data.text}</p>
          {!run.data.ai && <p className="mt-1 text-[11px] text-canvas-muted">Zeki AI cevap vermedi; öneri kuraldan yazıldı.</p>}
        </>
      ) : (
        <p className="text-[12px] text-canvas-muted">Okulun profili, son notlar, siparişler ve uygun kitaplardan 2–3 cümlelik hazırlık notu.</p>
      )}
    </Block>
  );
}

function AddPlan({ id, today, onDone }: { id: string; today: string; onDone: () => void }) {
  const qc = useQueryClient();
  const [day, setDay] = useState(addDays(today, 1));
  const run = useMutation({
    mutationFn: () => schoolsApi.addPlan(id, { gun: day }),
    onSuccess: (p) => {
      toast.success(p.conflicts.length ? 'Plana eklendi — o gün takvimde tatil/sınav var, kontrol edin.' : 'Plana eklendi.');
      invalidateSchools(qc);
      onDone();
    },
    onError: (e) => toast.error(errText(e, 'Eklenemedi.') ?? 'Eklenemedi.'),
  });
  return (
    <section className="glass-panel flex flex-wrap items-end gap-2 rounded-2xl p-3 shadow-glass-float sm:rounded-3xl">
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Ziyaret günü</span>
        <input type="date" className={field} value={day} min={today} onChange={(e) => setDay(e.target.value)} />
      </label>
      <button type="button" className={btnPrimary} onClick={() => run.mutate()} disabled={!day || run.isPending}>
        Plana ekle
      </button>
      <button type="button" className={btnGhost} onClick={onDone}>
        Vazgeç
      </button>
    </section>
  );
}

const GRADES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13];
const gradeName = (g: number) => (g === 0 ? 'Okul öncesi' : g === 13 ? 'Yetişkin' : `${g}.`);

function CatalogPanel({ detail, canVisit, canExport }: { detail: SchoolDetail; canVisit: boolean; canExport: boolean }) {
  const qc = useQueryClient();
  const s = detail.school;
  const [grades, setGrades] = useState<number[]>(s.grades);
  const [cap, setCap] = useState('');
  const [size, setSize] = useState<string>('20');
  const [result, setResult] = useState<Catalog | null>(null);
  const body = (preview: boolean) => ({
    siniflar: grades,
    fiyatUst: cap ? Number(cap.replace(',', '.')) : null,
    adet: size === 'hepsi' ? ('hepsi' as const) : Number(size),
    onizleme: preview,
  });
  const preview = useMutation({ mutationFn: () => schoolsApi.catalog(s.id, body(true)), onSuccess: setResult });
  const make = useMutation({
    mutationFn: async () => {
      const c = await schoolsApi.catalog(s.id, body(false));
      if (c.id && canExport) await downloadCatalog(c.id);
      return c;
    },
    onSuccess: (c) => {
      setResult(c);
      toast.success(canExport ? 'Katalog PDF indirildi.' : 'Katalog kaydedildi; PDF indirme yetkiniz yok.');
      invalidateSchools(qc);
    },
    onError: (e) => toast.error(errText(e, 'Katalog hazırlanamadı.') ?? 'Katalog hazırlanamadı.'),
  });
  const toggle = (g: number) => setGrades((cur) => (cur.includes(g) ? cur.filter((x) => x !== g) : [...cur, g].sort((a, b) => a - b)));
  const shown = s.grades.length ? GRADES.filter((g) => s.grades.includes(g) || grades.includes(g)) : GRADES;
  return (
    <Block title="Katalog (kademeye uygun, stokta)" action={<SqlInfo k={detail.kaynaklar} alan="catalogs" label="Hazırlanan kataloglar" />}>
      <p className="mb-2 text-[11.5px] leading-snug text-canvas-muted">Sınıfları seçin; «Listeyi göster» kitapları ekranda gösterir, «PDF hazırla» okula bırakabileceğiniz kataloğu indirir.</p>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Sınıflar">
        {shown.map((g) => (
          <button
            key={g}
            type="button"
            aria-pressed={grades.includes(g)}
            onClick={() => toggle(g)}
            className={`inline-flex min-h-11 min-w-11 items-center justify-center rounded-xl px-2.5 text-[12.5px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-9 ${
              grades.includes(g) ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink'
            }`}
          >
            {gradeName(g)}
          </button>
        ))}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 sm:max-w-md">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>En yüksek fiyat (₺)</span>
          <input className={field} inputMode="decimal" value={cap} onChange={(e) => setCap(e.target.value)} placeholder="Örn. 150 (boş: sınır yok)" />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kitap sayısı</span>
          <select className={field} value={size} onChange={(e) => setSize(e.target.value)}>
            {['10', '20', '30', '50'].map((x) => (
              <option key={x}>{x}</option>
            ))}
            <option value="hepsi">Uygun olanların hepsi</option>
          </select>
        </label>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" className={btnGhost} onClick={() => preview.mutate()} disabled={!grades.length || preview.isPending || !canVisit}>
          {preview.isPending ? 'Seçiliyor…' : 'Listeyi göster'}
        </button>
        <button type="button" className={btnPrimary} onClick={() => make.mutate()} disabled={!grades.length || make.isPending || !canVisit}>
          <FileDown aria-hidden className="h-4 w-4" />
          {make.isPending ? 'Hazırlanıyor…' : 'PDF hazırla'}
        </button>
      </div>
      {preview.error && <div className="mt-2"><Note tone="err">{errText(preview.error, 'Liste seçilemedi.')}</Note></div>}
      {result && (
        <div className="mt-3">
          <p className="flex flex-wrap items-center gap-1 text-[12px] font-semibold text-canvas-muted">
            Uygun ve stokta {fmtNum(result.total)} kitaptan {fmtNum(result.items.length)} tanesi; sıra ildeki bayilerin satışına göre.
            <SqlInfo k={result.kaynaklar} alan="total" label="Katalog seçimi" />
            <span className="inline-flex items-center gap-0.5">
              stok
              <SqlInfo k={result.kaynaklar} alan="items[].stock" label="Stok bakiyesi" />
            </span>
            <span className="inline-flex items-center gap-0.5">
              fiyat
              <SqlInfo k={result.kaynaklar} alan="items[].price" label="Fiyat" />
            </span>
          </p>
          {result.warning && <div className="mt-1"><Note tone="warn">{result.warning}</Note></div>}
          <ol className="mt-2 divide-y divide-slate-100 rounded-xl border border-slate-100 bg-white/85">
            {result.items.map((b) => (
              <li key={b.code} className="flex items-start justify-between gap-3 px-3 py-2">
                <div className="min-w-0">
                  <div className="text-[12.5px] font-bold leading-snug">{b.title ?? b.code}</div>
                  <div className="text-[11px] text-canvas-muted">
                    {b.grades} · {b.pages ? `${b.pages} sayfa · ` : ''}stok {fmtNum(b.stock)}
                  </div>
                </div>
                <div className="shrink-0 text-right font-mono text-[12px] font-bold tabular-nums" title={b.priceBasis ?? undefined}>
                  {fmtMoney(b.price)}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
      {detail.catalogs.length > 0 && (
        <div className="mt-3 text-[11.5px] text-canvas-muted">
          Daha önce hazırlananlar:{' '}
          {detail.catalogs.map((k, i) => (
            <span key={k.id}>
              {i ? ', ' : ''}
              {canExport ? (
                <button type="button" className="font-bold text-canvas-violet underline" onClick={() => downloadCatalog(k.id).catch((e) => toast.error(errText(e, 'İndirilemedi.') ?? 'İndirilemedi.'))}>
                  {fmtDay(k.at)} ({k.count} kitap)
                </button>
              ) : (
                `${fmtDay(k.at)} (${k.count} kitap)`
              )}
            </span>
          ))}
        </div>
      )}
    </Block>
  );
}

function Visits({ c }: { c: SchoolDetail }) {
  const crm = useShowMore(c.crmVisits, 30);
  return (
    <Block
      title="Ziyaretler"
      action={
        <span className="flex items-center gap-1 text-[11px] font-semibold text-canvas-muted">
          Portal
          <SqlInfo k={c.kaynaklar} alan="portalVisits" label="Portal ziyaret raporları" />
          CRM
          <SqlInfo k={c.kaynaklar} alan="crmVisits" label="CRM okul ziyaretleri" />
        </span>
      }
    >
      <p className="text-[11.5px] leading-snug text-canvas-muted">
        CRM'de tamamlanan okul ziyareti: {c.crmDoneLinked} (ziyaret yeri bağlı)
        {c.crmDoneByName ? ` + ${c.crmDoneByName} (okul adı eşleşmesiyle)` : ''}.
        <SqlInfo k={c.kaynaklar} alan="crmDoneLinked" label="Tamamlanan CRM ziyareti" />
        {c.hiddenOthers ? ` Başka temsilcilerin ${c.hiddenOthers} portal raporu size görünmez.` : ''}
        {c.hiddenOthers ? <SqlInfo k={c.kaynaklar} alan="hiddenOthers" label="Görünmeyen portal raporu" /> : null}
      </p>
      <ul className="mt-2 space-y-1.5">
        {c.portalVisits.map((v) => (
          <li key={v.id} className="rounded-xl border border-slate-100 bg-white/85 px-3 py-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[12.5px] font-bold">{fmtDay(v.day)}</span>
              <Pill tone="violet">Portal</Pill>
              {v.interestLabel && <Pill tone={v.interest === 'yuksek' ? 'ok' : v.interest === 'dusuk' ? 'err' : 'muted'}>İlgi {v.interestLabel.toLocaleLowerCase('tr')}</Pill>}
              {v.roleLabel && <Pill tone="muted">{v.roleLabel}</Pill>}
              <span className="text-[11px] text-canvas-muted">{v.ownerName}</span>
            </div>
            {v.hidden ? (
              <p className="mt-1 text-[11.5px] italic text-canvas-muted">Not yalnız yazana açık.</p>
            ) : (
              v.note && <p className="mt-1 whitespace-pre-line text-[12px] leading-snug">{v.note}</p>
            )}
            {v.books.length > 0 && <p className="mt-1 text-[11.5px]">İstenen: {v.books.map((b) => b.title ?? b.code).join(', ')}</p>}
            {v.routed && <p className="mt-0.5 text-[11.5px]">Bayiye yönlendirildi: {v.routedDealer}</p>}
            {v.next && (
              <p className="mt-0.5 text-[11.5px] font-semibold">
                Sıradaki adım: {v.next}
                {v.nextDay ? ` (${fmtDay(v.nextDay)})` : ''}
              </p>
            )}
          </li>
        ))}
        {crm.shown.map((v, i) => (
          <li key={v.id ?? i} className="rounded-xl border border-slate-100 bg-white/70 px-3 py-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[12.5px] font-bold">{fmtDay(v.day)}</span>
              <Pill tone="muted">CRM</Pill>
              <Pill tone={v.done ? 'ok' : 'muted'}>{v.statusLabel}</Pill>
              {v.matchedBy === 'ad' && <Pill tone="warn">ad eşleşmesi</Pill>}
              <span className="text-[11px] text-canvas-muted">{[v.typeLabel, v.formLabel, v.ownerName].filter(Boolean).join(' · ')}</span>
            </div>
            {(v.dealer || v.participants || v.sold) && (
              <p className="mt-0.5 text-[11.5px] text-canvas-muted">
                {[v.dealer ? `Aracı: ${v.dealer}` : null, v.participants ? `${v.participants} katılımcı` : null, v.sold ? `${v.sold} kitap satıldı` : null]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            )}
          </li>
        ))}
      </ul>
      <ShowMoreButton more={crm} noun="CRM ziyareti" />
      {!c.portalVisits.length && !c.crmVisits.length && <p className="text-[12px] text-canvas-muted">Bu okula kayıtlı ziyaret yok. Ziyaret sonrası «Ziyaret raporu gir» ile kaydedebilirsiniz.</p>}
    </Block>
  );
}

function Orders({ c }: { c: SchoolDetail }) {
  return (
    <Block title="Okul örneği ve okul satışı" action={<SqlInfo k={c.kaynaklar} alan="orders" label="Okul siparişleri" />}>
      <p className="text-[11.5px] leading-snug text-canvas-muted">{c.ordersNote}</p>
      {c.orders.length ? (
        <ul className="mt-2 space-y-1">
          {c.orders.map((o, i) => (
            <li key={o.id ?? i} className="flex flex-wrap items-baseline justify-between gap-2 rounded-xl bg-white/85 px-3 py-1.5">
              <span className="text-[12.5px] font-bold">
                {o.typeLabel} · {fmtDay(o.day)}
              </span>
              <span className="font-mono text-[12px] tabular-nums">
                {o.qty != null ? `${fmtNum(o.qty)} adet · ` : ''}
                {fmtMoney(o.amount)}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-[12px] text-canvas-muted">Bu okulla eşleşen örnek kitap ya da okul satışı siparişi yok.</p>
      )}
    </Block>
  );
}
