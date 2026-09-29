import { useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ArrowRight, CheckCircle2, ExternalLink, Search, TriangleAlert } from 'lucide-react';
import { Note, Pill, field, nf } from '../../../admin/ui';
import SqlInfo, { InfoLabel } from '../../../components/SqlInfo';
import { Kpi, KpiRow, Panel, useDebounced } from '../../kit';
import { day, errMsg } from '../ui';
import { compareApi, type ClauseRow, type Detail, type FormalCheck, type Meta, type TextRow } from './api';
import { band, pct, periodOptions, statusTone, textTone, visibleClauses } from './compare';
import { TONE } from './ScanTab';
import { ReviewButton } from './Review';

/**
 * Tek sözleşme: kıyas grubu (hangi ölçütle, kaç emsal, neyi gevşettik), madde madde değer ↔ emsal dağılımı ve
 * gerekçe, serbest metinli özel maddeler, aynı hak sahibinin önceki sözleşmesinden farklar ve emsal listesi.
 */
export default function ContractTab({ meta, contractKey, onPick }: { meta: Meta; contractKey: string; onPick: (id: string) => void }) {
  const [years, setYears] = useState<number | undefined>(undefined);
  const [onlyDiff, setOnlyDiff] = useState(true);
  const q = useQuery({
    queryKey: ['contracts', 'compare', 'contract', meta.gorunum.okunduAn, contractKey, years],
    queryFn: () => compareApi.contract(contractKey, years),
    enabled: !!contractKey,
    placeholderData: keepPreviousData,
  });
  const d = q.data;
  return (
    <>
      <Picker onPick={(id) => { setYears(undefined); onPick(id); }} />
      {!contractKey && (
        <Panel>
          <p className="py-8 text-center text-[12.5px] text-canvas-muted">
            Bir sözleşme seçin ya da «Olağan dışı sözleşmeler» listesinden birine dokunun. Portal kaydı ve yüklenen belge, kendi sayfasındaki «Emsalle karşılaştır» bağlantısıyla açılır.
          </p>
        </Panel>
      )}
      {q.error && <Note tone="err">{errMsg(q.error)}</Note>}
      {contractKey && q.isLoading && <Panel><p className="py-10 text-center text-[12.5px] text-canvas-muted">Emsaller okunuyor…</p></Panel>}
      {d && (
        <div className={`flex flex-col gap-3 transition-opacity duration-150 ease-out lg:gap-4 ${q.isFetching ? 'opacity-70' : ''}`}>
          <Head d={d} meta={meta} years={years ?? d.ayar.yil} onYears={setYears} />
          {d.warnings.map((w) => <Note key={w} tone="warn">{w}</Note>)}
          <KpiRow>
            <Kpi label="Farklı madde" value={nf.format(d.sayim.sapan)} help="Emsalden yüksek/düşük, nadir ya da eksik"
              info={<SqlInfo k={d.kaynaklar} alan="sayim" label="Farklı madde" />} />
            <Kpi label="Emsalle uyumlu" value={nf.format(d.sayim.uyumlu)} help="Emsallerin olağan aralığında"
              info={<SqlInfo k={d.kaynaklar} alan="sayim" label="Emsalle uyumlu" />} />
            <Kpi label="Özgün not" value={nf.format(d.sayim.ozgunNot)} help="Serbest metni başka sözleşmede yok"
              info={<SqlInfo k={d.kaynaklar} alan="texts[]" label="Özgün not" />} />
            <Kpi label="Emsal" value={nf.format(d.criteria.emsal)} help={`${nf.format(d.criteria.sozlesme)} CRM kaydı (grup kopyaları dahil)`}
              info={<SqlInfo k={d.kaynaklar} alan="criteria" label="Emsal" />} />
          </KpiRow>
          <Panel>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-[15px] font-extrabold">
                <InfoLabel k={d.kaynaklar} alan="groups[]" label="Maddeler">Maddeler</InfoLabel>
              </h2>
              <label className="flex min-h-11 items-center gap-2 text-[12.5px] font-bold sm:min-h-0">
                <input type="checkbox" className="h-4 w-4 accent-canvas-violet" checked={onlyDiff} onChange={(e) => setOnlyDiff(e.target.checked)} />
                Yalnız farklı maddeler
              </label>
            </div>
            {d.groups.map((g) => {
              const rows = visibleClauses(g.clauses, onlyDiff);
              if (!rows.length) return null;
              return (
                <section key={g.id} className="mt-3">
                  <h3 className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{g.label}</h3>
                  <ul className="mt-1.5 divide-y divide-slate-100 rounded-2xl border border-slate-100 bg-white/85">
                    {rows.map((c) => <ClauseLine key={c.key} c={c} contractKey={d.subject.key} canReview={d.can.review} />)}
                  </ul>
                </section>
              );
            })}
            {onlyDiff && d.sayim.sapan === 0 && (
              <p className="py-6 text-center text-[12.5px] text-canvas-muted">Bütün maddeler emsalle uyumlu. Hepsini görmek için süzgeci kaldırın.</p>
            )}
          </Panel>
          {d.sekil.length > 0 && <Formal d={d} />}
          {d.texts.length > 0 && <Texts d={d} />}
          <History d={d} />
          <Peers d={d} />
        </div>
      )}
    </>
  );
}

function Picker({ onPick }: { onPick: (id: string) => void }) {
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const dq = useDebounced(q.trim(), 300);
  const found = useQuery({
    queryKey: ['contracts', 'compare', 'search', dq, page],
    queryFn: () => compareApi.search(dq, page),
    enabled: dq.length >= 2,
    placeholderData: keepPreviousData,
  });
  const items = dq.length >= 2 ? found.data?.items ?? [] : [];
  return (
    <Panel>
      <label className="relative block">
        <span className="sr-only">Sözleşme ara</span>
        <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
        <input className={`${field} pl-9`} value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder="Karşılaştırılacak sözleşme: numara, kitap ya da yazar" />
      </label>
      {found.error && <Note tone="err">{errMsg(found.error)}</Note>}
      {items.length > 0 && (
        <>
          <ul className="mt-2 max-h-72 divide-y divide-slate-100 overflow-y-auto overscroll-contain rounded-2xl border border-slate-100 bg-white/90">
            {items.map((x) => (
              <li key={x.id}>
                <button
                  type="button"
                  className="flex min-h-11 w-full items-center justify-between gap-2 px-3 py-2 text-left text-[12.5px] hover:bg-violet-50/60"
                  onClick={() => { setQ(''); setPage(0); onPick(x.id); }}
                >
                  <span className="min-w-0">
                    <span className="font-mono text-[12px] font-bold text-canvas-violet">{x.no}</span>{' '}
                    <span className="font-bold">{x.kitap || '—'}</span>
                    <span className="block truncate text-[11.5px] text-canvas-muted">{[x.yazar, x.yil, x.odeme].filter(Boolean).join(' · ')}</span>
                  </span>
                  <ArrowRight aria-hidden className="h-4 w-4 shrink-0 text-canvas-muted" />
                </button>
              </li>
            ))}
          </ul>
          <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-[11px] text-canvas-muted">
            <InfoLabel k={found.data?.kaynaklar} alan="total" label="Eşleşen sözleşme">
              {`${nf.format(found.data?.total ?? 0)} eşleşme · ${nf.format(page * (found.data?.pageSize ?? 20) + 1)}–${nf.format(page * (found.data?.pageSize ?? 20) + items.length)}`}
            </InfoLabel>
            <span className="flex gap-3">
              {page > 0 && <button type="button" className="min-h-11 font-bold text-canvas-violet sm:min-h-0" onClick={() => setPage((n) => n - 1)}>Önceki</button>}
              {(page + 1) * (found.data?.pageSize ?? 20) < (found.data?.total ?? 0) && (
                <button type="button" className="min-h-11 font-bold text-canvas-violet sm:min-h-0" onClick={() => setPage((n) => n + 1)}>Sonraki</button>
              )}
            </span>
          </div>
        </>
      )}
      {dq.length >= 2 && found.data && !items.length && <p className="mt-2 text-[12px] text-canvas-muted">Eşleşen sözleşme yok.</p>}
    </Panel>
  );
}

function Head({ d, meta, years, onYears }: { d: Detail; meta: Meta; years: number; onYears: (y: number) => void }) {
  const s = d.subject;
  const c = d.criteria;
  const link = s.kaynak === 'crm' || s.kaynak === 'portal' ? `/telif-sozlesme/${s.key}` : null;
  return (
    <Panel>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[13px] font-bold text-canvas-violet">{s.no}</span>
            <Pill tone="muted">{s.kaynak === 'crm' ? 'CRM' : s.kaynak === 'portal' ? 'Portal kaydı' : 'Yüklenen belge'}</Pill>
            {s.durum && <Pill tone="muted">{s.durum}</Pill>}
          </div>
          <h2 className="mt-1 break-words text-[17px] font-extrabold leading-snug">{s.baslik}</h2>
          <p className="mt-0.5 text-[12px] text-canvas-muted">
            {[s.yazar, s.tip, s.odeme, s.para, s.bolum, s.bas ? `${day(s.bas)}${s.bit ? ` – ${day(s.bit)}` : ''}` : s.yil].filter(Boolean).join(' · ')}
          </p>
          {s.kopyalar.length > 1 && (
            <p className="mt-1 text-[11.5px] text-canvas-muted">{`Aynı şartlı ${s.kopyalar.length} kitap kaydı: ${s.kopyalar.map((k) => k.no).join(', ')}`}</p>
          )}
          {link && (
            <Link to={link} className="mt-1 inline-flex min-h-11 items-center gap-1 text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0">
              Sözleşme sayfası
              <ExternalLink aria-hidden className="h-3.5 w-3.5" />
            </Link>
          )}
        </div>
        <div className="w-full shrink-0 rounded-2xl border border-slate-100 bg-white/80 p-3 lg:w-[380px]">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
              <InfoLabel k={d.kaynaklar} alan="criteria" label="Kıyas grubu">Kıyas grubu</InfoLabel>
            </span>
            <select aria-label="Emsal dönemi" className={`${field} w-auto py-1`} value={years} onChange={(e) => onYears(Number(e.target.value))}>
              {periodOptions(meta.ayarlar.yil).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <dl className="mt-2 space-y-1 text-[12px]">
            {c.boyutlar.map((b) => (
              <div key={b.id} className="flex justify-between gap-2">
                <dt className="text-canvas-muted">{b.ad}</dt>
                <dd className="text-right font-semibold">{b.deger ?? '—'}</dd>
              </div>
            ))}
            <div className="flex justify-between gap-2">
              <dt className="text-canvas-muted">{c.donem.ad}</dt>
              <dd className="text-right font-semibold">{c.donem.deger}</dd>
            </div>
          </dl>
          {c.gevsetilen.length > 0 && (
            <p className="mt-2 text-[11.5px] leading-snug text-amber-800">{`Emsal ${meta.ayarlar.emsal}'den azdı; gevşetilen ölçüt: ${c.gevsetilen.join(', ')}.`}</p>
          )}
          {c.bilinmeyen.length > 0 && (
            <p className="mt-1 text-[11.5px] leading-snug text-canvas-muted">{`Bu kayıtta bilinmeyen ölçüt: ${c.bilinmeyen.join(', ')} (kıyasa girmedi).`}</p>
          )}
          {!c.yeterli && <p className="mt-1 text-[11.5px] font-semibold text-rose-700">Bütün ölçütler gevşetildiği hâlde emsal az; kararlar temkinli okunmalı.</p>}
          {c.kur && <p className="mt-1 text-[11.5px] leading-snug text-canvas-muted">{c.kur}</p>}
        </div>
      </div>
    </Panel>
  );
}

function ClauseLine({ c, contractKey, canReview }: { c: ClauseRow; contractKey: string; canReview: boolean }) {
  const tone = statusTone(c.status);
  const b = c.kind !== 'secim' && c.kind !== 'bayrak' ? band({ ...c, value: c.kind === 'tutar' ? c.kiyas ?? null : c.value }) : null;
  const deviates = ['yuksek', 'dusuk', 'nadir', 'nadir-madde', 'eksik'].includes(c.status);
  return (
    <li className="grid gap-2 p-3 text-[12.5px] sm:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] sm:gap-4">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-bold">{c.label}</span>
          <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${TONE[tone]}`}>{c.statusLabel}</span>
        </div>
        <div className="mt-1 break-words font-mono text-[15px] font-bold tabular-nums">{c.valueLabel}</div>
        {c.reason && <p className="mt-1 text-[11.5px] leading-snug text-canvas-muted">{c.reason}</p>}
        {(deviates || c.inceleme) && (
          <div className="mt-1.5">
            <ReviewButton contractKey={contractKey} clause={c.key} title={c.label} value={c.valueLabel} current={c.inceleme} can={canReview} />
          </div>
        )}
      </div>
      <div className="min-w-0">
        {b ? (
          <Band c={c} b={b} tone={tone} />
        ) : (
          c.enSik && c.enSik.length > 0 && (
            <ul className="space-y-1">
              {c.enSik.map((t) => (
                <li key={String(t.deger)} className="flex items-center gap-2 text-[11.5px]">
                  <span className="w-28 shrink-0 truncate font-semibold">{t.ad}</span>
                  <span className="relative h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-slate-100">
                    <span className="absolute inset-y-0 left-0 rounded-full bg-slate-400" style={{ width: `${Math.max(2, (t.pay ?? 0) * 100)}%` }} />
                  </span>
                  <span className="w-12 shrink-0 text-right font-mono tabular-nums text-canvas-muted">{pct(t.pay)}</span>
                </li>
              ))}
            </ul>
          )
        )}
        <p className="mt-1 text-[11px] text-canvas-muted">
          {c.kind === 'secim' || c.kind === 'bayrak'
            ? `${nf.format(c.n)} emsal`
            : `${nf.format(c.dolu ?? 0)}/${nf.format(c.n)} emsalde dolu`}
          {c.kind === 'tutar' && c.valueLabel.includes('≈') && ` · kıyas ${c.kiyasBirim ?? 'USD'} üzerinden`}
        </p>
      </div>
    </li>
  );
}

function Band({ c, b, tone }: { c: ClauseRow; b: NonNullable<ReturnType<typeof band>>; tone: string }) {
  const dot = tone === 'err' ? 'bg-rose-600' : tone === 'warn' ? 'bg-amber-500' : 'bg-canvas-violet';
  return (
    <div>
      <div className="relative h-6" aria-label={`Emsal aralığı ${c.p10Ad ?? '—'} – ${c.p90Ad ?? '—'}, medyan ${c.medyanAd ?? '—'}, bu sözleşme ${c.valueLabel}`} role="img">
        <span className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-slate-100" />
        <span className="absolute top-1/2 h-2 -translate-y-1/2 rounded-full bg-slate-300" style={{ left: `${b.lo * 100}%`, width: `${Math.max(1, (b.hi - b.lo) * 100)}%` }} />
        {b.med != null && <span className="absolute top-1/2 h-4 w-0.5 -translate-y-1/2 bg-slate-600" style={{ left: `calc(${b.med * 100}% - 1px)` }} />}
        {b.value != null && (
          <span className={`absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full border-2 border-white shadow ${dot}`} style={{ left: `calc(${b.value * 100}% - 7px)` }} />
        )}
      </div>
      <div className="flex justify-between gap-2 font-mono text-[10.5px] tabular-nums text-canvas-muted">
        <span>{c.enAzAd ?? '—'}</span>
        <span className="truncate">{`%10–%90: ${c.p10Ad ?? '—'} – ${c.p90Ad ?? '—'} · medyan ${c.medyanAd ?? '—'}`}</span>
        <span>{c.enCokAd ?? '—'}</span>
      </div>
    </div>
  );
}

function Formal({ d }: { d: Detail }) {
  const bad = d.sekil.filter((x) => !x.ok);
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-extrabold">
          <InfoLabel k={d.kaynaklar} alan="sekil[]" label="Şekil denetimi">Şekil denetimi</InfoLabel>
        </h2>
        <span className={`rounded-md px-2 py-0.5 text-[11.5px] font-bold ${bad.length ? TONE.err : TONE.ok}`}>
          {bad.length ? `${bad.length} eksik` : 'Eksik yok'}
        </span>
      </div>
      <p className="mt-0.5 text-[11.5px] text-canvas-muted">Kaydın taşıması gereken şartlar. Hukuki görüş değildir; kayıt denetimidir.</p>
      <ul className="mt-2 divide-y divide-slate-100 rounded-2xl border border-slate-100 bg-white/85">
        {d.sekil.map((x) => <FormalLine key={x.id} x={x} contractKey={d.subject.key} canReview={d.can.review} />)}
      </ul>
    </Panel>
  );
}

function FormalLine({ x, contractKey, canReview }: { x: FormalCheck; contractKey: string; canReview: boolean }) {
  const Icon = x.ok ? CheckCircle2 : TriangleAlert;
  return (
    <li className="flex gap-2.5 p-3 text-[12.5px]">
      <Icon aria-hidden className={`mt-0.5 h-4 w-4 shrink-0 ${x.ok ? 'text-emerald-600' : 'text-rose-600'}`} />
      <div className="min-w-0">
        <div className="font-bold">{x.label}</div>
        {x.detail && <div className="text-[12px] text-rose-700">{x.detail}</div>}
        <div className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">{x.law}</div>
        {!x.ok && (
          <div className="mt-1.5">
            <ReviewButton contractKey={contractKey} clause={`sekil:${x.id}`} title={x.label} value={x.detail ?? 'Eksik'} current={x.inceleme} can={canReview} />
          </div>
        )}
      </div>
    </li>
  );
}

function Texts({ d }: { d: Detail }) {
  return (
    <Panel>
      <h2 className="text-[15px] font-extrabold">
        <InfoLabel k={d.kaynaklar} alan="texts[]" label="Serbest metinli maddeler">Serbest metinli maddeler</InfoLabel>
      </h2>
      <p className="mt-0.5 text-[11.5px] text-canvas-muted">CRM'deki açıklama alanları; başka sözleşmelerde birebir ya da çok benzer geçip geçmediği.</p>
      <ul className="mt-2 space-y-2">
        {d.texts.map((t) => <TextLine key={t.key} t={t} contractKey={d.subject.key} canReview={d.can.review} />)}
      </ul>
    </Panel>
  );
}

function TextLine({ t, contractKey, canReview }: { t: TextRow; contractKey: string; canReview: boolean }) {
  return (
    <li className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px]">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-bold">{t.label}</span>
        <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${TONE[textTone(t.status)]}`}>{t.statusLabel}</span>
        {t.sinif && (
          <span className="rounded-md bg-violet-50 px-1.5 py-0.5 text-[11px] font-bold text-violet-800" title="Haklar ve lisanslar ekranındaki sınıf">
            {`Hak kısıtı: ${t.sinif.ad}${t.sinif.durum === 'onayli' ? ' (onaylı)' : ''}`}
          </span>
        )}
        <span className="text-[11px] text-canvas-muted">
          {t.toplam === 0 ? 'Başka hiçbir sözleşmede yok' : `${nf.format(t.birebir)} sözleşmede birebir, ${nf.format(t.benzer)} sözleşmede benzeri`}
        </span>
      </div>
      <p className="mt-1.5 whitespace-pre-wrap break-words leading-snug">{t.text}</p>
      {(t.status === 'ozgun' || t.inceleme) && (
        <div className="mt-1.5">
          <ReviewButton contractKey={contractKey} clause={`not:${t.key}`} title={t.label} value={t.text.slice(0, 160)} current={t.inceleme} can={canReview} />
        </div>
      )}
      {t.ornekler.length > 0 && (
        <details className="mt-2">
          <summary className="min-h-11 cursor-pointer text-[12px] font-bold text-canvas-violet sm:min-h-0">Benzer metinler</summary>
          <ul className="mt-1.5 space-y-1.5">
            {t.ornekler.map((x) => (
              <li key={`${x.id}-${x.alan}`} className="rounded-xl bg-slate-50 p-2 text-[12px]">
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-canvas-muted">
                  <Link to={`/telif-sozlesme/${x.id}`} className="font-mono font-bold text-canvas-violet hover:underline">{x.no}</Link>
                  <span>{x.alanAd}</span>
                  <span>{`benzerlik ${pct(x.benzerlik)}`}</span>
                </div>
                <p className="mt-1 whitespace-pre-wrap break-words">{x.metin}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </li>
  );
}

function History({ d }: { d: Detail }) {
  const h = d.history;
  if (!h.items.length) {
    return (
      <Panel>
        <h2 className="text-[15px] font-extrabold">Aynı hak sahibinin öbür sözleşmeleri</h2>
        <p className="mt-1 text-[12.5px] text-canvas-muted">
          {h.taraflar.length ? `${h.taraflar.join(', ')} için başka sözleşme yok.` : 'Sözleşmede CRM taraf kaydı yok; hak sahibinin öbür sözleşmeleri bulunamadı.'}
        </p>
      </Panel>
    );
  }
  return (
    <Panel>
      <h2 className="text-[15px] font-extrabold">
        <InfoLabel k={d.kaynaklar} alan="history" label="Aynı hak sahibinin öbür sözleşmeleri">Aynı hak sahibinin öbür sözleşmeleri</InfoLabel>
      </h2>
      <p className="mt-0.5 text-[11.5px] text-canvas-muted">{`${h.taraflar.join(', ')} · ${h.items.length} sözleşme`}</p>
      {h.onceki && (
        <div className="mt-2 rounded-2xl border border-violet-100 bg-violet-50/40 p-3">
          <div className="text-[12.5px] font-bold">
            {'Önceki sözleşmeden farklar '}
            <Link to={`/telif-sozlesme/${h.onceki.id}`} className="font-mono text-canvas-violet hover:underline">{h.onceki.no}</Link>
            {h.onceki.bas && <span className="font-normal text-canvas-muted">{` · ${day(h.onceki.bas)}`}</span>}
          </div>
          {h.degisen.length ? (
            <ul className="mt-1.5 divide-y divide-violet-100 text-[12px]">
              {h.degisen.map((x) => (
                <li key={x.key} className="grid gap-1 py-1.5 sm:grid-cols-[minmax(0,200px)_minmax(0,1fr)] sm:gap-3">
                  <span className="font-semibold">{x.label}</span>
                  <span className="min-w-0 break-words">
                    <span className="text-canvas-muted line-through decoration-rose-400">{String(x.old ?? '—')}</span>
                    {' → '}
                    <span className="font-bold">{String(x.new ?? '—')}</span>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-[12px] text-canvas-muted">Maddeler önceki sözleşmeyle aynı.</p>
          )}
        </div>
      )}
      <div className="mt-2 overflow-x-auto overscroll-x-contain">
        <table className="w-full min-w-[560px] text-[12px]">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-canvas-muted">
              <th className="py-1.5 pr-3">Sözleşme</th>
              <th className="py-1.5 pr-3">Başlangıç</th>
              <th className="py-1.5 pr-3">Ödeme türü</th>
              <th className="py-1.5 pr-3 text-right">Karton telif</th>
              <th className="py-1.5 pr-3 text-right">Avans</th>
              <th className="py-1.5 text-right">Tek ödeme</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {h.items.map((x) => (
              <tr key={x.id}>
                <td className="py-1.5 pr-3">
                  <Link to={`/telif-sozlesme/${x.id}`} className="font-mono font-bold text-canvas-violet hover:underline">{x.no}</Link>
                  <div className="max-w-[240px] truncate text-[11px] text-canvas-muted">{x.kitap}</div>
                </td>
                <td className="py-1.5 pr-3 tabular-nums">{day(x.bas)}</td>
                <td className="py-1.5 pr-3">{x.odeme ?? '—'}</td>
                <td className="py-1.5 pr-3 text-right font-mono tabular-nums">{x.oran}</td>
                <td className="py-1.5 pr-3 text-right font-mono tabular-nums">{x.avans}</td>
                <td className="py-1.5 text-right font-mono tabular-nums">{x.tekOdeme}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function Peers({ d }: { d: Detail }) {
  const [shown, setShown] = useState(20);
  const list = d.peers.slice(0, shown);
  return (
    <Panel>
      <details>
        <summary className="min-h-11 cursor-pointer text-[15px] font-extrabold sm:min-h-0">
          <InfoLabel k={d.kaynaklar} alan="peers[]" label="Emsal sözleşmeler">{`Emsal sözleşmeler (${nf.format(d.peers.length)})`}</InfoLabel>
        </summary>
        <ul className="mt-2 divide-y divide-slate-100 text-[12px]">
          {list.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-2 py-1.5">
              <span className="min-w-0">
                <Link to={`/telif-sozlesme/${p.id}`} className="font-mono font-bold text-canvas-violet hover:underline">{p.no}</Link>{' '}
                <span className="break-words">{p.kitap}</span>
                <span className="block truncate text-[11px] text-canvas-muted">{[p.yazar, p.yil, p.kopya > 1 ? `${p.kopya} kitap` : null].filter(Boolean).join(' · ')}</span>
              </span>
            </li>
          ))}
        </ul>
        {shown < d.peers.length && (
          <button type="button" className="mt-2 min-h-11 text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0" onClick={() => setShown((n) => n + 50)}>
            {`Daha fazla göster (${nf.format(d.peers.length - shown)} kaldı)`}
          </button>
        )}
      </details>
    </Panel>
  );
}
