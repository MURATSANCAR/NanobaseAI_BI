import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, FileSpreadsheet, Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, nf, td, th } from '../../admin/ui';
import Sheet from '../../editorial/studio/reader/Sheet';
import { fmtDay } from '../hrApi';
import { Block, Fact, HrFrame, Tabs } from '../parts';
import SqlInfo from '../../components/SqlInfo';
import Calibration from './Calibration';
import { REVIEW_TONE, perfApi, pct, type Cycle, type Form, type PerfMeta, type Section } from './perfApi';

/** M56 Değerlendirme dönemi (İK): dönem aç/kapat, form şablonu, tamamlanma panosu, tek tıkla hatırlatma, kalibrasyon.
 *  Kalibrasyon ve kişi adlı dağılım yalnız kalibrasyon yetkisinde. */

type Tab = 'donem' | 'durum' | 'kalibrasyon' | 'form';

export default function ReviewCycle() {
  const meta = useQuery({ queryKey: ['hr', 'perf', 'meta'], queryFn: perfApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const cycles = useQuery({ queryKey: ['hr', 'perf', 'cycles'], queryFn: perfApi.cycles, enabled: ENGINE_ENABLED });
  const [tab, setTab] = useState<Tab>('durum');
  const [sel, setSel] = useState<string>('');
  useEffect(() => {
    if (!sel && cycles.data?.items.length) setSel((cycles.data.items.find((c) => c.state === 'acik') ?? cycles.data.items[0]).id);
  }, [cycles.data, sel]);
  const can = meta.data?.me.can;
  const tabs = [
    { key: 'durum' as const, label: 'Tamamlanma' },
    { key: 'donem' as const, label: 'Dönemler' },
    ...(can?.calibration ? [{ key: 'kalibrasyon' as const, label: 'Kalibrasyon' }] : []),
    ...(can?.cycle ? [{ key: 'form' as const, label: 'Formlar' }] : []),
  ];
  const cycle = cycles.data?.items.find((c) => c.id === sel);
  return (
    <HrFrame
      crumb="Değerlendirme dönemi"
      title="Değerlendirme dönemi"
      lead="Değerlendirme dönemini açın, kimin nerede kaldığını izleyin ve hatırlatın. Sıra: öz değerlendirme → yönetici değerlendirmesi → görüşme ve paylaşım → çalışan yorumu → İK onayı. Puanı sistem vermez; yönetici verir."
      aside={cycles.data && cycles.data.items.length > 0 ? (
        <select className={field} value={sel} onChange={(e) => setSel(e.target.value)} aria-label="Dönem">
          {cycles.data.items.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.stateLabel}</option>)}
        </select>
      ) : undefined}
    >
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {cycles.error && <Note tone="err">{errText(cycles.error, 'Dönemler okunamadı.')}</Note>}
      {tab === 'durum' && (cycle ? <StatusTab cycle={cycle} meta={meta.data} /> : cycles.data && <Note tone="info">Henüz değerlendirme dönemi yok.{can?.cycle ? ' «Dönemler» sekmesinden yeni dönem açın.' : ''}</Note>)}
      {tab === 'donem' && meta.data && <CyclesTab items={cycles.data?.items ?? []} meta={meta.data} onPick={(id) => { setSel(id); setTab('durum'); }} />}
      {tab === 'kalibrasyon' && cycle && <Calibration cycleId={cycle.id} />}
      {tab === 'form' && <FormsTab />}
    </HrFrame>
  );
}

function StatusTab({ cycle, meta }: { cycle: Cycle; meta?: PerfMeta }) {
  const qc = useQueryClient();
  const st = useQuery({ queryKey: ['hr', 'perf', 'status', cycle.id], queryFn: () => perfApi.status(cycle.id) });
  const [unit, setUnit] = useState('');
  const act = useMutation({
    mutationFn: (a: 'open' | 'calibrate' | 'reopen' | 'close') => perfApi.cycleAction(cycle.id, a),
    onSuccess: (r) => { toast.success(`${r.stateLabel}${r.added ? ` · ${r.added} kişi eklendi` : ''}`); void qc.invalidateQueries({ queryKey: ['hr', 'perf'] }); },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.')),
  });
  const sync = useMutation({ mutationFn: () => perfApi.sync(cycle.id), onSuccess: (r) => { toast.success(`${r.added} kişi eklendi.`); void st.refetch(); },
    onError: (e) => toast.error(errText(e, 'Eşitlenemedi.')) });
  const remind = useMutation({
    mutationFn: (which: 'self' | 'manager') => perfApi.remind(cycle.id, which),
    onSuccess: (r) => toast.success(`${r.sent} kişiye hatırlatma gitti${r.noMail ? `, ${r.noMail} kişinin iş e-postası bulunamadı` : ''}${r.adRead ? '' : ' (dizin okunamadı)'}.`),
    onError: (e) => toast.error(errText(e, 'Hatırlatma gönderilemedi.')),
  });
  const can = meta?.me.can;
  const d = st.data;
  const people = (d?.people ?? []).filter((p) => !unit || p.unitName === unit);
  return (
    <div className="flex flex-col gap-3">
      {can?.cycle && (
        <div className="flex flex-wrap gap-2">
          {cycle.state === 'hazirlik' && <button type="button" className={btnPrimary} disabled={act.isPending} onClick={() => act.mutate('open')}>Dönemi aç</button>}
          {cycle.state === 'acik' && <button type="button" className={btnGhost} disabled={sync.isPending} onClick={() => sync.mutate()} title="Dönem açıldıktan sonra işe girenleri ekler, yöneticisi sonradan girilen kişiyi yöneticisine bağlar">Katılımcıları güncelle</button>}
          {cycle.state === 'acik' && <button type="button" className={btnGhost} disabled={remind.isPending} onClick={() => remind.mutate('self')}>Öz değerlendirmesi eksiklere e-posta gönder</button>}
          {cycle.state === 'acik' && <button type="button" className={btnGhost} disabled={remind.isPending} onClick={() => remind.mutate('manager')}>Yöneticilere e-posta gönder</button>}
          {cycle.state === 'acik' && <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate('calibrate')}>Kalibrasyona al</button>}
          {cycle.state === 'kalibrasyon' && <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate('reopen')}>Yeniden aç</button>}
          {(cycle.state === 'acik' || cycle.state === 'kalibrasyon') && <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate('close')}>Dönemi kapat</button>}
          {can.export && <button type="button" className={btnGhost} onClick={() => void perfApi.exportCycle(cycle.id).catch((e) => toast.error(errText(e, 'İndirilemedi.')))}><Download aria-hidden className="h-4 w-4" />Tabloyu indir (CSV)</button>}
          {can.export && <button type="button" className={btnGhost} onClick={() => void perfApi.exportCycleXlsx(cycle.id).catch((e) => toast.error(errText(e, 'İndirilemedi.')))}><FileSpreadsheet aria-hidden className="h-4 w-4" />Tabloyu indir (Excel)</button>}
        </div>
      )}
      {st.error && <Note tone="err">{errText(st.error, 'Durum okunamadı.')}</Note>}
      {st.isLoading && <Loading />}
      {d && (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <Fact label="Katılımcı" value={nf.format(d.total)} explain="Bu dönemde değerlendirilecek çalışan sayısı." info={<SqlInfo k={d.kaynaklar} alan="total" label="Katılımcı" />} />
            <Fact label="Öz değerlendirme" value={`${d.selfDone} · ${pct(d.selfRate)}`} help={cycle.selfDue ? `son ${fmtDay(cycle.selfDue)}` : undefined} info={<SqlInfo k={d.kaynaklar} alan="selfDone" label="Öz değerlendirme" />} />
            <Fact label="Yönetici değerlendirmesi" value={`${d.managerDone} · ${pct(d.managerRate)}`} help={cycle.managerDue ? `son ${fmtDay(cycle.managerDue)}` : undefined} info={<SqlInfo k={d.kaynaklar} alan="managerDone" label="Yönetici değerlendirmesi" />} />
            <Fact label="Paylaşılan" value={nf.format(d.shared)} explain="Yöneticinin görüşmeyi yapıp sonucu çalışanla paylaştığı değerlendirmeler." info={<SqlInfo k={d.kaynaklar} alan="shared" label="Paylaşılan" />} />
            <Fact label="Onaylanan" value={nf.format(d.approved)} explain="Çalışan yorumundan sonra İK’nın onayladığı, tamamlanmış değerlendirmeler." info={<SqlInfo k={d.kaynaklar} alan="approved" label="Onaylanan" />} />
            <Fact label="İtiraz" value={nf.format(d.objections)} help={d.noManager ? `${d.noManager} kişinin yöneticisi yok` : undefined}
              explain="Çalışanın paylaşılan değerlendirmeye yorumunda itiraz ettiği kayıtlar; İK onayından önce bakılmalı." info={<SqlInfo k={d.kaynaklar} alan="objections" label="İtiraz" />} />
          </div>
          <Block title="Birimler" help="Birim adına dokununca aşağıdaki kişi listesi o birime süzülür; yeniden dokununca süzgeç kalkar." info={<SqlInfo k={d.kaynaklar} alan="units" label="Birim tamamlanma" />}>
            <TableWrap>
              <thead><tr><th className={th}>Birim</th><th className={th}>Kişi</th><th className={th}>Öz değ.</th><th className={th}>Yönetici değ.</th><th className={th}>Onay</th></tr></thead>
              <tbody>
                {d.units.map((u) => (
                  <tr key={u.unitName} className="border-t border-slate-100">
                    <td className={td}><button type="button" className="font-bold text-canvas-violet hover:underline" onClick={() => setUnit(unit === u.unitName ? '' : u.unitName)}>{u.unitName}</button></td>
                    <td className={`${td} tabular-nums`}>{u.total}</td>
                    <td className={`${td} tabular-nums`}>{u.self} · {pct(u.total ? u.self / u.total : null)}</td>
                    <td className={`${td} tabular-nums`}>{u.manager} · {pct(u.total ? u.manager / u.total : null)}</td>
                    <td className={`${td} tabular-nums`}>{u.approved}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </Block>
          <Block title={unit ? `Kişiler · ${unit}` : 'Kişiler'} help="Kişiye dokunarak değerlendirmeyi açın (yetkinize göre).">
            <ul className="grid grid-cols-1 gap-1.5 md:grid-cols-2">
              {people.map((p) => (
                <li key={p.reviewId}>
                  <Link to={`/ik/degerlendirme/${p.reviewId}`} className="flex min-h-11 flex-wrap items-center gap-2 rounded-xl bg-white/80 px-3 py-2 text-[12.5px] transition-colors duration-150 hover:bg-white">
                    <span className="min-w-0 flex-1 break-words font-bold">{p.name}</span>
                    <span className="text-canvas-muted">{p.managerName ?? 'yöneticisiz'}</span>
                    {p.objection && <Pill tone="err">itiraz</Pill>}
                    <Pill tone={REVIEW_TONE[p.state]}>{p.stateLabel}</Pill>
                  </Link>
                </li>
              ))}
            </ul>
          </Block>
        </>
      )}
      {can?.cycle && meta && <SalesmanFill logoOn={meta.settings.logoSales} />}
    </div>
  );
}

function SalesmanFill({ logoOn }: { logoOn: boolean }) {
  const [year, setYear] = useState(new Date().getFullYear());
  const run = useMutation({ mutationFn: () => perfApi.salesmanFill(year), onError: (e) => toast.error(errText(e, 'Ölçülemedi.')) });
  return (
    <Block title="Satış hedeflerinde Logo ölçüsü" help={`Satış hedeflerinin ilerlemesi Logo'dan otomatik ölçülebilir mi: Logo satış faturalarında satış temsilcisi alanının ne kadar dolu olduğu. Oran yeterliyse yönetici ayarlardan «Hedefte Logo satış ölçüsü»nü açar. Şu an ${logoOn ? 'açık' : 'kapalı'}.`}
      action={
        <div className="flex gap-2">
          <input className={`${field} w-24`} inputMode="numeric" value={year} onChange={(e) => setYear(Number(e.target.value) || year)} aria-label="Yıl" />
          <button type="button" className={btnGhost} disabled={run.isPending} onClick={() => run.mutate()}>{run.isPending ? 'Ölçülüyor…' : 'Doluluğu ölç'}</button>
        </div>
      }>
      {run.data && (
        <div className="text-[13px]">{nf.format(run.data.invoices)} satış faturasının {nf.format(run.data.withSalesman)} tanesinde temsilci var · <b>{pct(run.data.rate)}</b>
          <SqlInfo k={run.data.kaynaklar} alan="rate" label="Temsilci alanı doluluğu" className="ml-0.5" /></div>
      )}
    </Block>
  );
}

function CyclesTab({ items, meta, onPick }: { items: Cycle[]; meta: PerfMeta; onPick: (id: string) => void }) {
  const [edit, setEdit] = useState<Cycle | 'new' | null>(null);
  return (
    <div className="flex flex-col gap-2">
      {meta.me.can.cycle && (
        <div className="flex justify-start">
          <button type="button" className={btnPrimary} onClick={() => setEdit('new')}><Plus aria-hidden className="h-4 w-4" />Yeni dönem</button>
        </div>
      )}
      {!items.length && <Note tone="info">Henüz değerlendirme dönemi yok.{meta.me.can.cycle ? ' «Yeni dönem» ile başlayın.' : ''}</Note>}
      <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {items.map((c) => (
          <li key={c.id} className="glass-panel flex flex-col gap-1 rounded-2xl p-3 shadow-glass-float">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="min-w-0 flex-1 break-words text-[14px] font-extrabold">{c.name}</span>
              <Pill tone={c.state === 'acik' ? 'ok' : c.state === 'kapandi' ? 'muted' : 'warn'}>{c.stateLabel}</Pill>
            </div>
            <div className="text-[11.5px] text-canvas-muted">Dönem {fmtDay(c.periodStart)} – {fmtDay(c.periodEnd)} · formlar {fmtDay(c.startsOn)} – {fmtDay(c.endsOn)}</div>
            <div className="text-[11.5px] text-canvas-muted">{c.form ? `${c.form.name} (sürüm ${c.form.version})` : 'Form seçilmedi'}{c.audience.units?.length ? ` · ${c.audience.units.length} birim` : ' · bütün çalışanlar'}</div>
            <div className="mt-1 flex flex-wrap gap-2">
              <button type="button" className={btnGhost} onClick={() => onPick(c.id)}>Durumu gör</button>
              {meta.me.can.cycle && c.state !== 'kapandi' && c.state !== 'kalibrasyon' && <button type="button" className={btnGhost} onClick={() => setEdit(c)}>Düzenle</button>}
            </div>
          </li>
        ))}
      </ul>
      {edit !== null && <CycleEditor c={edit === 'new' ? null : edit} meta={meta} onClose={() => setEdit(null)} />}
    </div>
  );
}

function CycleEditor({ c, meta, onClose }: { c: Cycle | null; meta: PerfMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const forms = useQuery({ queryKey: ['hr', 'perf', 'forms'], queryFn: perfApi.forms });
  const y = new Date().getFullYear();
  const [f, setF] = useState({
    name: c?.name ?? `${y} yıllık değerlendirme`, periodStart: c?.periodStart ?? `${y}-01-01`, periodEnd: c?.periodEnd ?? `${y}-12-31`,
    startsOn: c?.startsOn ?? '', endsOn: c?.endsOn ?? '', selfDue: c?.selfDue ?? '', managerDue: c?.managerDue ?? '',
    formTemplateId: c?.formTemplateId ?? '', units: c?.audience.units ?? ([] as string[]),
  });
  const save = useMutation({
    mutationFn: () => {
      const b: Record<string, unknown> = { ...f, selfDue: f.selfDue || null, managerDue: f.managerDue || null, formTemplateId: f.formTemplateId || null };
      if (c && c.state !== 'hazirlik') delete b.units;
      return c ? perfApi.updateCycle(c.id, b) : perfApi.createCycle(b);
    },
    onSuccess: () => { toast.success('Dönem kaydedildi.'); void qc.invalidateQueries({ queryKey: ['hr', 'perf', 'cycles'] }); onClose(); },
    onError: (e) => toast.error(errText(e, 'Dönem kaydedilemedi.')),
  });
  const locked = !!c && c.state !== 'hazirlik';
  const date = (k: 'periodStart' | 'periodEnd' | 'startsOn' | 'endsOn' | 'selfDue' | 'managerDue', l: string) => (
    <label className="flex flex-col gap-1">
      <span className={labelCls}>{l}</span>
      <input type="date" className={field} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
    </label>
  );
  return (
    <Sheet open modal wide onClose={onClose} title={c ? c.name : 'Yeni dönem'}>
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ad</span>
          <input className={field} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {date('periodStart', 'Değerlendirilen dönem başı')}{date('periodEnd', 'Değerlendirilen dönem sonu')}
          {date('startsOn', 'Formlar açılır')}{date('endsOn', 'Formlar kapanır')}
          {date('selfDue', 'Öz değerlendirme son')}{date('managerDue', 'Yönetici değerlendirmesi son')}
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Form (yürürlükte olan)</span>
          <select className={field} value={f.formTemplateId} disabled={locked} onChange={(e) => setF({ ...f, formTemplateId: e.target.value })}>
            <option value="">Seçin</option>
            {(forms.data?.items ?? []).map((x) => <option key={x.id} value={x.id} disabled={x.state !== 'yururlukte'}>{x.name} (s{x.version}) · {x.stateLabel}</option>)}
          </select>
        </label>
        <fieldset disabled={locked} className="flex flex-col gap-1">
          <span className={labelCls}>Hedef kitle (boş: bütün aktif çalışanlar; birim seçilirse alt birimleri de)</span>
          <div className="flex max-h-48 flex-col gap-1 overflow-y-auto rounded-xl bg-slate-50 p-2">
            {meta.units.map((u) => (
              <label key={u.id} className="flex min-h-9 items-center gap-2 text-[12.5px]">
                <input type="checkbox" checked={f.units.includes(u.id)} onChange={(e) => setF({ ...f, units: e.target.checked ? [...f.units, u.id] : f.units.filter((x) => x !== u.id) })} />
                {u.name}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={save.isPending || !f.name.trim() || !f.startsOn || !f.endsOn} onClick={() => save.mutate()}>Kaydet</button>
        </div>
      </div>
    </Sheet>
  );
}

function FormsTab() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['hr', 'perf', 'forms'], queryFn: perfApi.forms });
  const [edit, setEdit] = useState<Form | 'new' | null>(null);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-start"><button type="button" className={btnPrimary} onClick={() => setEdit('new')}><Plus aria-hidden className="h-4 w-4" />Yeni form</button></div>
      {q.error && <Note tone="err">{errText(q.error, 'Formlar okunamadı.')}</Note>}
      <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {(q.data?.items ?? []).map((f) => (
          <li key={f.id}>
            <button type="button" onClick={() => setEdit(f)} className="glass-panel flex w-full flex-col gap-1 rounded-2xl p-3 text-left shadow-glass-float">
              <div className="flex flex-wrap items-center gap-1.5"><span className="min-w-0 flex-1 text-[14px] font-extrabold">{f.name}</span><Pill tone={f.state === 'yururlukte' ? 'ok' : 'muted'}>{f.stateLabel}</Pill><span className="font-mono text-[11px]">sürüm {f.version}</span></div>
              <div className="text-[11.5px] text-canvas-muted">{f.sections.map((s) => s.title).join(' · ')}</div>
            </button>
          </li>
        ))}
      </ul>
      {edit !== null && q.data && <FormEditor f={edit === 'new' ? null : edit} starter={q.data.starter} onClose={() => { setEdit(null); void qc.invalidateQueries({ queryKey: ['hr', 'perf', 'forms'] }); }} />}
    </div>
  );
}

function FormEditor({ f, starter, onClose }: { f: Form | null; starter: { name: string; sections: Section[] }; onClose: () => void }) {
  const [name, setName] = useState(f?.name ?? starter.name);
  const [state, setState] = useState<Form['state']>(f?.state ?? 'taslak');
  const [text, setText] = useState(JSON.stringify(f?.sections ?? starter.sections, null, 2));
  const [labels, setLabels] = useState((f?.overallLabels ?? []).join('\n'));
  const save = useMutation({
    mutationFn: () => {
      let sections: unknown;
      try { sections = JSON.parse(text); } catch { throw new Error('Bölümler metni bozuk; tırnak, virgül ve parantezleri kontrol edin.'); }
      const overall = labels.split('\n').map((x) => x.trim()).filter(Boolean);
      const body: Record<string, unknown> = { name, state, sections, ...(overall.length ? { overallLabels: overall } : {}) };
      return f ? perfApi.updateForm(f.id, body) : perfApi.createForm(body);
    },
    onSuccess: () => { toast.success('Form kaydedildi.'); onClose(); },
    onError: (e) => toast.error(errText(e, 'Form kaydedilemedi.')),
  });
  return (
    <Sheet open modal wide onClose={onClose} title={f ? f.name : 'Yeni form'} subtitle="Kısa form önerilir: 3–5 hedef, 4–6 yetkinlik, iki açık uç. Bölümler değişince sürüm artar; açık dönem kendi kopyasını kullanır.">
      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1"><span className={labelCls}>Ad</span><input className={field} value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Durum</span>
            <select className={field} value={state} onChange={(e) => setState(e.target.value as Form['state'])}>
              <option value="taslak">Taslak</option><option value="yururlukte">Yürürlükte</option><option value="arsiv">Arşiv</option>
            </select>
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Bölümler (örnek yapıyı koruyarak düzenleyin: title = bölüm başlığı, kind = yetkinlik | hedef | acik, items = maddeler)</span>
          <textarea className={`${field} min-h-[260px] font-mono text-[12px]`} value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Genel değerlendirme ölçeği (5 satır; boşsa varsayılan)</span>
          <textarea className={`${field} min-h-[110px]`} value={labels} onChange={(e) => setLabels(e.target.value)} />
        </label>
        <div className="flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={save.isPending || !name.trim()} onClick={() => save.mutate()}>Kaydet</button>
        </div>
      </div>
    </Sheet>
  );
}
