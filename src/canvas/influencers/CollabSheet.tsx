import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, ExternalLink, Loader2, Mail, Sparkles } from 'lucide-react';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import SqlInfo from '../components/SqlInfo';
import Sheet from '../editorial/studio/reader/Sheet';
import {
  STAGE_TONE, fmtDay, fmtInt, fmtLeft, fmtMoney, inflApi, parseNum,
  type CollabDetail, type CollabInput, type Draft, type DraftKind, type Meta, type Stage,
} from './api';
import { AskSheet } from './parts';

/** Bir işbirliğinin bütün işi: aşama, bağlantı ve sonuç, onay, taslaklar, geçmiş. Telefonda alttan açılır. */
export default function CollabSheet({ id, meta, onClose }: { id: string | null; meta: Meta; onClose: () => void }) {
  const q = useQuery({ queryKey: ['influencers', 'collab', id], queryFn: () => inflApi.collab(id as string), enabled: !!id });
  const c = q.data;
  return (
    <Sheet open={!!id} modal wide onClose={onClose} title={c ? `${c.code} · ${c.personName ?? ''}` : 'İşbirliği'}
      subtitle={c ? `${c.bookTitle ?? 'Kitap'} · ${c.kindLabel}` : undefined}>
      {q.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
      {q.error && <Note tone="err">{errText(q.error, 'İşbirliği okunamadı.')}</Note>}
      {c && <Body c={c} meta={meta} />}
    </Sheet>
  );
}

type Form = { due: string; order: string; url: string; pubAt: string; disc: '' | 'var' | 'yok'; reach: string; eng: string; note: string; fee: string };

function formOf(c: CollabDetail): Form {
  return {
    due: c.duePublish ?? '', order: c.crmOrderNo ?? '', url: c.publishedUrl ?? '', pubAt: c.publishedAt ?? '',
    disc: c.disclosureOk === true ? 'var' : c.disclosureOk === false ? 'yok' : '', reach: c.reach?.toString() ?? '',
    eng: c.engagement?.toString() ?? '', note: c.resultNote ?? '', fee: c.fee?.toString() ?? '',
  };
}

function Body({ c, meta }: { c: CollabDetail; meta: Meta }) {
  const qc = useQueryClient();
  const me = meta.me;
  const [f, setF] = useState<Form>(() => formOf(c));
  useEffect(() => setF(formOf(c)), [c]);
  const [ask, setAsk] = useState<null | 'vazgec' | 'ret'>(null);
  const set = (k: keyof Form) => (v: string) => setF((x) => ({ ...x, [k]: v }));
  const refresh = () => qc.invalidateQueries({ queryKey: ['influencers'] });
  const closed = c.stage === 'kapali' || c.stage === 'vazgecildi';

  const payload = useMemo((): CollabInput => {
    const b: CollabInput = {
      duePublish: f.due || null, crmOrderNo: f.order, publishedUrl: f.url.trim() || null, resultNote: f.note,
      disclosureOk: f.disc === '' ? null : f.disc === 'var', reach: f.reach.trim() ? parseNum(f.reach) : null,
      engagement: f.eng.trim() ? parseNum(f.eng) : null,
    };
    if (f.pubAt) b.publishedAt = f.pubAt;
    if (me.canSeeFee && f.fee.trim() !== (c.fee?.toString() ?? '')) b.fee = parseNum(f.fee);
    return b;
  }, [f, me.canSeeFee, c.fee]);

  const save = useMutation({
    mutationFn: (extra: CollabInput) => inflApi.updateCollab(c.id, { ...payload, ...extra }),
    onSuccess: (_, extra) => {
      refresh();
      toast.success(extra.stage ? `Aşama: ${meta.asamalar[extra.stage]}` : 'Kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const approve = useMutation({
    mutationFn: (b: { decision: 'onay' | 'ret'; note?: string }) => inflApi.approveCollab(c.id, b.decision, b.note),
    onSuccess: (_, b) => { refresh(); setAsk(null); toast.success(b.decision === 'onay' ? 'Teklif onaylandı.' : 'Teklif reddedildi.'); },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.') ?? ''),
  });

  const idx = meta.pano.indexOf(c.stage);
  const next: Stage | null = closed ? null : c.stage === 'rapor' ? (c.feeSet ? 'odeme' : 'kapali') : c.stage === 'odeme' ? null : (meta.pano[idx + 1] ?? null);
  const prev: Stage | null = !closed && idx > 0 && c.stage !== 'odeme' ? meta.pano[idx - 1] : null;

  return (
    <div className="flex flex-col gap-4 text-[13px]">
      <div className="flex flex-wrap items-center gap-1.5">
        <Pill tone={STAGE_TONE[c.stage]}>{c.stageLabel}</Pill>
        {c.waitingApproval && <Pill tone="warn">Onay bekliyor</Pill>}
        {c.approvedBy && <Pill tone="ok">Onaylayan: {c.approvedBy}</Pill>}
        {c.linkLate && <Pill tone="err">Bağlantı gecikti</Pill>}
        {c.person.minor && <Pill tone="warn">Reşit değil — veli onayı</Pill>}
        <SqlInfo k={c.kaynaklar} alan="fee" label="Ücret, erişim, etkileşim ve ödeme" />
        <Link to={`/isbirlikleri/kisi/${c.personId}`} className="text-[12px] font-bold text-canvas-violet hover:underline">Kişi kartı</Link>
        {c.crmBookId && <Link to={`/kitap/${c.crmBookId}`} className="text-[12px] font-bold text-canvas-violet hover:underline">Kitap</Link>}
      </div>

      {c.waitingApproval && me.canApprove && (
        <div className="flex flex-wrap items-center gap-2 rounded-2xl bg-amber-50 p-3">
          <span className="min-w-0 flex-1 text-[12.5px]">Seçim ve teklif onayınızı bekliyor{c.fee !== null ? ` · ${fmtMoney(c.fee)}` : ''}. Teklifi açan onaylayamaz.</span>
          <button type="button" className={btnPrimary} disabled={approve.isPending} onClick={() => approve.mutate({ decision: 'onay' })}>
            <Check aria-hidden className="h-4 w-4" /> Onayla
          </button>
          <button type="button" className={btnGhost} onClick={() => setAsk('ret')}>Reddet</button>
        </div>
      )}

      {!closed && me.canEdit && (
        <div className="flex flex-wrap gap-2">
          {next && (
            <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate({ stage: next })}>
              {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
              {meta.asamalar[next]} olarak işaretle
            </button>
          )}
          {prev && <button type="button" className={btnGhost} onClick={() => save.mutate({ stage: prev })}>Geri: {meta.asamalar[prev]}</button>}
          {c.stage !== 'odeme' && <button type="button" className={btnGhost} onClick={() => setAsk('vazgec')}>Vazgeç</button>}
        </div>
      )}
      {c.stage === 'odeme' && <Note tone="info">Ödeme satırı muhasebede; ödeme Logo belge numarasıyla işaretlenince iş kendiliğinden kapanır.</Note>}

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Planlanan yayın" hint={fmtLeft(c.daysToPublish)}>
          <input type="date" className={field} value={f.due} disabled={closed || !me.canEdit} onChange={(e) => set('due')(e.target.value)} />
        </Field>
        <Field label="CRM tanıtım siparişi no" hint="Birden çoksa virgülle">
          <input className={field} value={f.order} disabled={closed || !me.canEdit} onChange={(e) => set('order')(e.target.value)} />
        </Field>
        <Field label="Paylaşım bağlantısı" hint="«Yayında» için şart">
          <input className={field} inputMode="url" placeholder="https://" value={f.url} disabled={closed || !me.canEdit} onChange={(e) => set('url')(e.target.value)} />
        </Field>
        <Field label="Yayın günü">
          <input type="date" className={field} value={f.pubAt} disabled={closed || !me.canEdit} onChange={(e) => set('pubAt')(e.target.value)} />
        </Field>
        <Field label="Yasal etiket (işbirliği/reklam)" hint={meta.ayarlar.disclosureKinds.includes(c.kind) ? 'Rapor için «var» şart' : undefined}>
          <select className={field} value={f.disc} disabled={closed || !me.canEdit} onChange={(e) => set('disc')(e.target.value)}>
            <option value="">İşaretlenmedi</option>
            <option value="var">Var</option>
            <option value="yok">Yok — düzeltme istendi</option>
          </select>
        </Field>
        {me.canSeeFee ? (
          <Field label="Ücret (₺, KDV hariç)">
            <input className={`${field} font-mono`} inputMode="decimal" value={f.fee} disabled={closed || c.stage === 'odeme'} onChange={(e) => set('fee')(e.target.value)} />
          </Field>
        ) : (
          <Field label="Ücret"><div className="py-2 text-[12.5px] text-canvas-muted">{c.feeSet ? 'girildi (görme yetkiniz yok)' : 'yok'}</div></Field>
        )}
        <Field label="Erişim">
          <input className={`${field} font-mono`} inputMode="numeric" value={f.reach} disabled={closed || !me.canEdit} onChange={(e) => set('reach')(e.target.value)} />
        </Field>
        <Field label="Etkileşim" hint="Beğeni + yorum + kaydetme + paylaşım">
          <input className={`${field} font-mono`} inputMode="numeric" value={f.eng} disabled={closed || !me.canEdit} onChange={(e) => set('eng')(e.target.value)} />
        </Field>
        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className={labelCls}>Sonuç notu</span>
          <textarea className={`${field} min-h-[56px]`} value={f.note} disabled={closed || !me.canEdit} onChange={(e) => set('note')(e.target.value)} />
        </label>
      </section>
      {!closed && me.canEdit && (
        <div className="flex flex-wrap items-center justify-end gap-2">
          {c.publishedUrl && (
            <a href={c.publishedUrl} target="_blank" rel="noreferrer" className={btnGhost}><ExternalLink aria-hidden className="h-4 w-4" /> Paylaşımı aç</a>
          )}
          <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate({})}>Kaydet</button>
        </div>
      )}
      {c.cpe !== null && <div className="text-right font-mono text-[12px] text-canvas-muted">Etkileşim başı maliyet {fmtMoney(c.cpe)}</div>}
      {c.payout && (
        <Note tone="info">Ödeme #{c.payout.no}: {c.payout.statusLabel}{c.payout.amount !== null ? ` · ${fmtMoney(c.payout.amount)}` : ''}{c.payout.logoDocNo ? ` · Logo ${c.payout.logoDocNo}` : ''}</Note>
      )}

      <Drafts c={c} meta={meta} />

      <section>
        <h3 className="mb-1.5 text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted">Geçmiş</h3>
        <ol className="flex flex-col gap-1">
          {c.events.map((e, i) => (
            <li key={i} className="flex flex-wrap gap-x-2 text-[12px] leading-snug">
              <span className="font-mono text-canvas-muted">{fmtDay(e.at)}</span>
              <span className="font-bold">{e.user}</span>
              <span className="min-w-0 break-words">{e.note ?? e.action}</span>
            </li>
          ))}
        </ol>
      </section>

      <AskSheet
        open={ask !== null}
        title={ask === 'ret' ? 'Teklifi reddet' : 'İşbirliğinden vazgeç'}
        message={ask === 'ret' ? 'Reddedilen teklif «vazgeçildi» olur. Nedeni işbirliği geçmişine yazılır.' : 'İş kapanır; kişi kartında «vazgeçildi» olarak kalır.'}
        confirm={ask === 'ret' ? 'Reddet' : 'Vazgeç'}
        danger
        input="Neden"
        required
        busy={save.isPending || approve.isPending}
        onClose={() => setAsk(null)}
        onConfirm={(text) => (ask === 'ret' ? approve.mutate({ decision: 'ret', note: text }) : save.mutate({ stage: 'vazgecildi', reason: text }, { onSuccess: () => setAsk(null) }))}
      />
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className={labelCls}>{label}</span>
      {children}
      {hint && <span className="text-[11px] leading-snug text-canvas-muted">{hint}</span>}
    </label>
  );
}

function Drafts({ c, meta }: { c: CollabDetail; meta: Meta }) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ['influencers', 'collab', c.id] });
  const make = useMutation({
    mutationFn: (k: DraftKind) => inflApi.draft(c.id, k),
    onSuccess: (d) => { refresh(); toast.success(`${d.kindLabel} taslağı hazır${d.source === 'zeki' ? ' (Zeki AI)' : ''}.`); },
    onError: (e) => toast.error(errText(e, 'Taslak hazırlanamadı.') ?? ''),
  });
  return (
    <section className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted">Brief ve yazışma taslakları</h3>
        {meta.me.canEdit && c.stage !== 'vazgecildi' && (
          <div className="flex flex-wrap gap-1.5">
            {(Object.keys(meta.taslakTurleri) as DraftKind[]).map((k) => (
              <button key={k} type="button" className={btnGhost} disabled={make.isPending} onClick={() => make.mutate(k)}>
                {make.isPending && make.variables === k ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                {meta.taslakTurleri[k]}
              </button>
            ))}
          </div>
        )}
      </div>
      <p className="text-[11.5px] leading-snug text-canvas-muted">
        Zeki AI yalnız serbest paragrafı yazar; kaynakta olmayan rakam ya da alıntı içeren cümle düşer. Yasal etiket maddesi şablonda sabittir.
        Portal içerik üreticisine e-posta göndermez: onaylı taslağı kendi e-postanızla gönderip «Gönderdim» ile kaydedin.
      </p>
      {c.drafts.length === 0 && <div className="text-[12px] text-canvas-muted">Henüz taslak yok.</div>}
      {c.drafts.map((d) => <DraftCard key={d.id} d={d} c={c} meta={meta} onChange={refresh} />)}
    </section>
  );
}

function DraftCard({ d, c, meta, onChange }: { d: Draft; c: CollabDetail; meta: Meta; onChange: () => void }) {
  const [body, setBody] = useState(d.body);
  useEffect(() => setBody(d.body), [d.body]);
  const edit = useMutation({ mutationFn: () => inflApi.editDraft(c.id, d.id, { body }), onSuccess: () => { onChange(); toast.success('Taslak kaydedildi.'); }, onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? '') });
  const approve = useMutation({ mutationFn: () => inflApi.approveDraft(c.id, d.id), onSuccess: () => { onChange(); toast.success('Taslak onaylandı.'); }, onError: (e) => toast.error(errText(e, 'Onaylanamadı.') ?? '') });
  const mailed = useMutation({ mutationFn: () => inflApi.markMailed(c.id, d.id), onSuccess: () => { onChange(); toast.success('Gönderildi olarak kaydedildi.'); }, onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? '') });
  const mailto = c.person.email && !c.person.doNotContact
    ? `mailto:${c.person.email}?subject=${encodeURIComponent(d.subject ?? '')}&body=${encodeURIComponent(d.body)}`
    : null;
  const editable = d.status === 'taslak' && meta.me.canEdit;
  return (
    <div className="rounded-2xl border border-slate-100 bg-white/80 p-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[13px] font-extrabold">{d.kindLabel}</span>
        <Pill tone={d.status === 'onayli' ? 'ok' : 'muted'}>{d.status === 'onayli' ? `Onaylı · ${d.approvedBy}` : 'Taslak'}</Pill>
        <Pill tone="violet">{d.source === 'zeki' ? 'Zeki AI' : d.source === 'elle' ? 'Düzenlendi' : 'Şablon'}</Pill>
        {d.sentAt && <Pill tone="ok">Gönderildi · {fmtDay(d.sentAt)}</Pill>}
        {d.dropped.length > 0 && <span className="text-[11px] text-canvas-muted">{d.dropped.length} cümle denetimde düştü</span>}
      </div>
      <textarea className={`${field} mt-2 min-h-[180px] font-mono text-[12px] leading-relaxed`} value={body} readOnly={!editable} onChange={(e) => setBody(e.target.value)} />
      <div className="mt-2 flex flex-wrap justify-end gap-2">
        {editable && body !== d.body && <button type="button" className={btnGhost} disabled={edit.isPending} onClick={() => edit.mutate()}>Değişikliği kaydet</button>}
        {d.status === 'taslak' && meta.me.canApprove && body === d.body && (
          <button type="button" className={btnPrimary} disabled={approve.isPending} onClick={() => approve.mutate()}><Check aria-hidden className="h-4 w-4" /> Onayla</button>
        )}
        {d.status === 'onayli' && mailto && (
          <a href={mailto} className={btnGhost}><Mail aria-hidden className="h-4 w-4" /> E-posta programında aç</a>
        )}
        {d.status === 'onayli' && !d.sentAt && meta.me.canEdit && (
          <button type="button" className={btnPrimary} disabled={mailed.isPending} onClick={() => mailed.mutate()}>Gönderdim</button>
        )}
      </div>
    </div>
  );
}

export function CollabCardBody({ c, showFee }: { c: { bookTitle: string | null; personName: string | null; kindLabel: string; duePublish: string | null; daysToPublish: number | null; fee: number | null; engagement: number | null; code: string }; showFee: boolean }) {
  return (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[11px] text-canvas-muted">{c.code}</span>
        <span className="text-[11px] text-canvas-muted">{c.kindLabel}</span>
      </div>
      <div className="mt-0.5 break-words text-[13px] font-extrabold leading-snug">{c.personName}</div>
      <div className="line-clamp-2 break-words text-[12px] leading-snug text-canvas-muted">{c.bookTitle ?? 'Kitap'}</div>
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11.5px]">
        {c.duePublish && <span className="font-mono tabular-nums">{fmtDay(c.duePublish)}</span>}
        {c.daysToPublish !== null && c.daysToPublish >= -30 && c.daysToPublish <= 7 && <span className="text-canvas-muted">{fmtLeft(c.daysToPublish)}</span>}
        {showFee && c.fee !== null && c.fee > 0 && <span className="font-mono tabular-nums">{fmtMoney(c.fee)}</span>}
        {c.engagement !== null && <span className="font-mono tabular-nums">{fmtInt(c.engagement)} etkileşim</span>}
      </div>
    </>
  );
}
