import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { CalendarClock, Plus, Search, ShieldAlert } from 'lucide-react';
import Sheet from '../editorial/studio/reader/Sheet';
import { Loading, Note, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel, useDebounced } from '../editorial/kit';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { ENGINE_ENABLED } from '../engine';
import { NewOpportunitySheet } from './OppForm';
import { Empty, StagePill } from './parts';
import {
  OPEN_STAGES,
  STAGE_ORDER,
  corporateApi,
  dueText,
  daysUntil,
  fmtMoney,
  fmtPct,
  fmtShort,
  type Meta,
  type Opportunity,
  type Stage,
} from './api';

/** Kaybedildi işaretlenirken neden zorunlu (kazanma/kaybetme analizi bununla yapılır). */
export function LostSheet({ open, loss, busy, onClose, onConfirm }: {
  open: boolean;
  loss: Record<string, string>;
  busy?: boolean;
  onClose: () => void;
  onConfirm: (cls: string, text: string) => void;
}) {
  const [cls, setCls] = useState('');
  const [text, setText] = useState('');
  return (
    <Sheet open={open} modal onClose={() => { setCls(''); setText(''); onClose(); }} title="Fırsat kaybedildi" subtitle="Neden seçin; gelecek yıl aynı kuruma dönüldüğünde burada görünür.">
      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-1.5" role="radiogroup" aria-label="Neden">
          {Object.entries(loss).map(([k, v]) => (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={cls === k}
              onClick={() => setCls(k)}
              className={`min-h-11 rounded-xl px-2 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] ${cls === k ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink'}`}
            >
              {v}
            </button>
          ))}
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Açıklama (isteğe bağlı)</span>
          <textarea className={`${field} min-h-[80px]`} value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        <div className="flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={`${btnPrimary} !bg-red-600`} disabled={!cls || busy} onClick={() => onConfirm(cls, text.trim())}>
            Kaybedildi olarak kapat
          </button>
        </div>
      </div>
    </Sheet>
  );
}

/** Fırsat kartı. Tutar ve karar günü «i»si bağlantının dışındadır (iç içe tıklanabilir öğe olmasın). */
function OppCard({ o, meta, showOwner, onStage, k }: { o: Opportunity; meta: Meta; showOwner: boolean; onStage: (o: Opportunity, s: Stage) => void; k?: Kaynaklar }) {
  const due = o.asama !== 'kazanildi' && o.asama !== 'kaybedildi' ? dueText(o.kararTarihi) : null;
  const late = (daysUntil(o.kararTarihi) ?? 1) < 0;
  const value = o.sonTeklif?.toplamNet ?? o.deger;
  const to = `/kurumsal-satis/firsat/${o.id}`;
  return (
    <li className="rounded-xl border border-slate-100 bg-white/90 p-3">
      <div className="flex items-start justify-between gap-2">
        <Link to={to} className="block min-w-0 flex-1">
          <div className="break-words text-[13px] font-extrabold leading-snug">{o.kurum}</div>
          <div className="break-words text-[12px] leading-snug text-canvas-muted">{o.ad}{o.tema ? ` · ${o.tema}` : ''}</div>
        </Link>
        <div className="inline-flex shrink-0 items-center text-right font-mono text-[12.5px] font-bold tabular-nums">
          {value ? fmtShort(value) : '—'}
          <SqlInfo k={k} alan="items[]" label="Fırsat değeri (son teklif ya da tahmini)" className="ml-0.5" />
        </div>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px]">
        {o.onayBekliyor && (
          <span className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-1.5 py-0.5 font-bold text-amber-800">
            <ShieldAlert aria-hidden className="h-3 w-3" /> Onay bekliyor
          </span>
        )}
        {o.sonTeklif && <span className="rounded-md bg-slate-100 px-1.5 py-0.5 font-bold">Teklif v{o.sonTeklif.surum} · {o.sonTeklif.durumLabel}</span>}
        {due && (
          <span className="inline-flex items-center">
            <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-bold ${late ? 'bg-red-50 text-red-700' : 'bg-slate-50 text-canvas-muted'}`}>
              <CalendarClock aria-hidden className="h-3 w-3" /> Karar {due}
            </span>
            <SqlInfo k={k} alan="kalanGun" label="Karara kalan gün" className="ml-0.5" />
          </span>
        )}
        {o.kayipSinifLabel && <span className="rounded-md bg-red-50 px-1.5 py-0.5 font-bold text-red-700">{o.kayipSinifLabel}</span>}
        {showOwner && <span className="text-canvas-muted">{o.sahip}</span>}
      </div>
      {meta.me.canQuote && (
        <label className="mt-2 flex items-center gap-2">
          <span className="sr-only">Aşama</span>
          <select
            className={`${field} !py-1.5`}
            value={o.asama}
            onChange={(e) => onStage(o, e.target.value as Stage)}
            aria-label={`${o.kurum} fırsatının aşaması`}
          >
            {STAGE_ORDER.map((s) => (
              <option key={s} value={s}>{meta.stages[s]}</option>
            ))}
          </select>
        </label>
      )}
    </li>
  );
}

export default function Pipeline({ meta, onReminders }: { meta: Meta; onReminders: () => void }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 250);
  const [all, setAll] = useState(false);
  const [phoneStage, setPhoneStage] = useState<Stage>('aday');
  const [creating, setCreating] = useState(false);
  const [losing, setLosing] = useState<Opportunity | null>(null);

  const list = useQuery({
    queryKey: ['corporate', 'opps', dq, all],
    queryFn: () => corporateApi.opportunities({ q: dq, acik: !all }),
    enabled: ENGINE_ENABLED,
  });
  const summary = useQuery({ queryKey: ['corporate', 'pipeline-summary'], queryFn: corporateApi.pipelineSummary, enabled: ENGINE_ENABLED });
  const rem = useQuery({ queryKey: ['corporate', 'reminders', 'acik'], queryFn: () => corporateApi.reminders({ durum: 'acik' }), enabled: ENGINE_ENABLED });

  const invalidate = () => qc.invalidateQueries({ queryKey: ['corporate'] });
  const create = useMutation({
    mutationFn: corporateApi.createOpportunity,
    onSuccess: (o) => {
      setCreating(false);
      invalidate();
      toast.success('Fırsat açıldı.');
      nav(`/kurumsal-satis/firsat/${o.id}`);
    },
    onError: (e) => toast.error(errText(e, 'Fırsat açılamadı.') ?? ''),
  });
  const stage = useMutation({
    mutationFn: ({ id, b }: { id: string; b: Parameters<typeof corporateApi.updateOpportunity>[1] }) => corporateApi.updateOpportunity(id, b),
    onSuccess: (o) => {
      setLosing(null);
      invalidate();
      toast.success(`${o.kurum}: ${o.asamaLabel}`);
    },
    onError: (e) => toast.error(errText(e, 'Aşama değişmedi.') ?? ''),
  });
  const onStage = (o: Opportunity, s: Stage) => {
    if (s === o.asama) return;
    if (s === 'kaybedildi') setLosing(o);
    else stage.mutate({ id: o.id, b: { asama: s } });
  };

  const stages = all ? STAGE_ORDER : OPEN_STAGES;
  const byStage = useMemo(() => {
    const m = new Map<Stage, Opportunity[]>();
    for (const s of STAGE_ORDER) m.set(s, []);
    for (const o of list.data?.items ?? []) m.get(o.asama)?.push(o);
    return m;
  }, [list.data]);
  const col = (s: Stage) => list.data?.columns.find((c) => c.asama === s);
  const err = errText(list.error, 'Fırsatlar okunamadı.');

  return (
    <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_340px] xl:gap-4">
      <Panel>
        <div className="flex flex-wrap items-end gap-2">
          <label className="relative min-w-[200px] flex-1">
            <span className="sr-only">Ara</span>
            <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
            <input className={`${field} pl-9`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kurum, fırsat ya da tema" />
          </label>
          <label className="inline-flex min-h-11 items-center gap-2 text-[12.5px] font-bold">
            <input type="checkbox" className="h-4 w-4" checked={all} onChange={(e) => setAll(e.target.checked)} />
            Kapananlar da
          </label>
          {meta.me.canQuote && (
            <button type="button" className={btnPrimary} onClick={() => setCreating(true)}>
              <Plus aria-hidden className="h-4 w-4" /> Yeni fırsat aç
            </button>
          )}
        </div>
        <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
          Açık fırsatlar aşamalarına göre dizilir: {OPEN_STAGES.map((s) => meta.stages[s]).join(' → ')}. Kazanılan ve kaybedilenleri «Kapananlar da» ile görürsünüz; aşamayı kartın altındaki listeden değiştirin.
        </p>
        {!meta.me.seeAll && <p className="mt-1 text-[11.5px] text-canvas-muted">Yalnız sizin fırsatlarınız ve onayınızı bekleyenler görünür.</p>}
        {err && <div className="mt-3"><Note tone="err">{err}</Note></div>}
        {list.isLoading && <Loading />}

        {list.data && list.data.items.length === 0 && (
          <div className="mt-3">
            <Empty title={dq ? 'Aramaya uyan fırsat yok' : 'Henüz fırsat yok'}>
              Yeni fırsatı buradan ya da «Hatırlatmalar»dan (geçen yıl bu dönemde alan kurumlar) açabilirsiniz.
            </Empty>
          </div>
        )}

        {list.data && list.data.items.length > 0 && (
          <>
            {/* Telefon: aşama seçici + tek liste. */}
            <div className="mt-3 lg:hidden">
              <div className="-mx-1 overflow-x-auto px-1">
                <div className="flex w-max gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Aşama">
                  {stages.map((s) => (
                    <button
                      key={s}
                      type="button"
                      role="tab"
                      aria-selected={phoneStage === s}
                      onClick={() => setPhoneStage(s)}
                      className={`min-h-11 whitespace-nowrap rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 ${phoneStage === s ? 'bg-canvas-violet text-white' : 'text-canvas-ink'}`}
                    >
                      {meta.stages[s]} <span className="font-mono tabular-nums opacity-80">{col(s)?.sayi ?? 0}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="mt-1 flex items-center gap-1 text-[11px] text-canvas-muted">
                Aşama sayıları ve değerleri
                <SqlInfo k={list.data.kaynaklar} alan="columns[]" label="Aşama başına fırsat sayısı ve değer" />
              </div>
              <ul className="mt-2 flex flex-col gap-2">
                {(byStage.get(phoneStage) ?? []).map((o) => (
                  <OppCard key={o.id} o={o} meta={meta} showOwner={meta.me.seeAll} onStage={onStage} k={list.data?.kaynaklar} />
                ))}
                {(byStage.get(phoneStage) ?? []).length === 0 && <li className="py-6 text-center text-[12px] text-canvas-muted">Bu aşamada fırsat yok. Üstten başka bir aşama seçin.</li>}
              </ul>
            </div>
            {/* Masaüstü: aşama sütunları (kendi kabında yatay kayar). */}
            <div className="mt-3 hidden overflow-x-auto lg:block">
              <div className="grid min-w-[980px] gap-3" style={{ gridTemplateColumns: `repeat(${stages.length}, minmax(220px, 1fr))` }}>
                {stages.map((s) => (
                  <section key={s} aria-label={meta.stages[s]} className="flex min-w-0 flex-col gap-2 rounded-2xl bg-slate-50/80 p-2">
                    <header className="flex items-baseline justify-between px-1">
                      <StagePill stage={s} label={meta.stages[s]} />
                      <span className="inline-flex items-center font-mono text-[11.5px] font-bold tabular-nums text-canvas-muted">
                        {col(s)?.sayi ?? 0} · {fmtShort(col(s)?.deger ?? 0)}
                        <SqlInfo k={list.data?.kaynaklar} alan="columns[]" label={`${meta.stages[s]}: fırsat sayısı ve değer`} className="ml-0.5" />
                      </span>
                    </header>
                    <ul className="flex flex-col gap-2">
                      {(byStage.get(s) ?? []).map((o) => (
                        <OppCard key={o.id} o={o} meta={meta} showOwner={meta.me.seeAll} onStage={onStage} k={list.data?.kaynaklar} />
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            </div>
          </>
        )}
      </Panel>

      <aside className="flex flex-col gap-3">
        <Panel>
          <h2 className="inline-flex items-center gap-1 text-[14px] font-extrabold">
            Yaklaşan kararlar
            <SqlInfo k={list.data?.kaynaklar} alan="kalanGun" label="Yaklaşan kararlar: kalan gün" />
          </h2>
          <p className="text-[11.5px] text-canvas-muted">Karar tarihi 7 gün içinde ya da geçmiş açık fırsatlar.</p>
          <ul className="mt-2 flex flex-col gap-1.5">
            {(list.data?.yaklasan ?? []).map((o) => (
              <li key={o.id}>
                <Link to={`/kurumsal-satis/firsat/${o.id}`} className="flex min-h-11 items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2 hover:bg-white">
                  <span className="min-w-0 truncate text-[12.5px] font-bold">{o.kurum}</span>
                  <span className={`shrink-0 text-[11.5px] font-bold ${(daysUntil(o.kararTarihi) ?? 1) < 0 ? 'text-red-700' : 'text-canvas-muted'}`}>{dueText(o.kararTarihi)}</span>
                </Link>
              </li>
            ))}
            {list.data && list.data.yaklasan.length === 0 && <li className="text-[12px] text-canvas-muted">Önümüzdeki 7 günde karar tarihi olan açık fırsat yok.</li>}
          </ul>
        </Panel>
        <Panel>
          <h2 className="text-[14px] font-extrabold">Dönemsel hatırlatma</h2>
          <p className="text-[11.5px] leading-snug text-canvas-muted">
            Geçen yıl bu dönemde alım yapan ve henüz aranmamış kurumlar ({meta.settings.reminderLeadDays} gün öncesinden).
          </p>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="inline-flex items-center font-mono text-[24px] font-bold tabular-nums">
              {rem.data ? rem.data.items.length : '—'}
              <SqlInfo k={rem.data?.kaynaklar} alan="items[]" label="Açık hatırlatma sayısı" className="ml-1" />
            </span>
            <span className="inline-flex items-center text-[12px] text-canvas-muted">
              geçen yıl {rem.data ? fmtShort(rem.data.toplamGecenYil) : '—'}
              <SqlInfo k={rem.data?.kaynaklar} alan="toplamGecenYil" label="Hatırlatmaların geçen yıl tutarı" className="ml-0.5" />
            </span>
          </div>
          <button type="button" className={`${btnGhost} mt-2 w-full`} onClick={onReminders}>Hatırlatmaları aç</button>
        </Panel>
        {summary.data && summary.data.kapanan > 0 && (
          <Panel>
            <h2 className="inline-flex items-center gap-1 text-[14px] font-extrabold">
              Kazanma ve kaybetme
              <SqlInfo k={summary.data.kaynaklar} alan="kazanmaOrani" label="Kazanma oranı, kazanılan değer ve nedenler" />
            </h2>
            <p className="text-[11.5px] text-canvas-muted">
              {summary.data.kapanan} kapanan fırsatın {summary.data.kazanilan}'i kazanıldı ({fmtPct(summary.data.kazanmaOrani)}), {fmtMoney(summary.data.kazanilanDeger)}.
            </p>
            <ul className="mt-2 flex flex-col gap-1">
              {summary.data.nedenler.map((n) => (
                <li key={n.kod} className="flex items-center justify-between text-[12px]">
                  <span>{n.label}</span>
                  <span className="font-mono font-bold tabular-nums">{n.sayi}</span>
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </aside>

      <NewOpportunitySheet open={creating} onClose={() => setCreating(false)} vocabulary={meta.vocabulary} busy={create.isPending} onCreate={(b) => create.mutate(b)} />
      <LostSheet
        open={!!losing}
        loss={meta.loss}
        busy={stage.isPending}
        onClose={() => setLosing(null)}
        onConfirm={(cls, text) => losing && stage.mutate({ id: losing.id, b: { asama: 'kaybedildi', kayipSinif: cls, kaybetmeNedeni: text } })}
      />
    </div>
  );
}
