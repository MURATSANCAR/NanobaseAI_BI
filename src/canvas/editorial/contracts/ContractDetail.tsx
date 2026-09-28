import { useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, Download, FilePen, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Note, Pill, btnGhost, btnPrimary, field } from '../../admin/ui';
import { ModuleFrame, Panel } from '../kit';
import { contractApi, detailKey, downloadDocx, metaOptions, type Detail, type Meta, type Status, type Terms } from './api';
import TermsForm from './TermsForm';
import DocumentExtract from './DocumentExtract';
import { extractApi, stillApplied, type Suggestion } from './extract';
import AddendaTab from './AddendaTab';
import PaymentsTab from './PaymentsTab';
import StatementsTab from './StatementsTab';
import TextTab from './TextTab';
import ContractRuns from '../royalty/ContractRuns';
import { changedFields, show } from './terms';
import { Field, Row, Sheet, Tabs, day, errMsg, money, num, stamp, statusTone, today } from './ui';

/** M6: tek sözleşmenin sayfası. Adres CRM kimliği ya da portal kaydı kimliğidir; CRM sözleşmesi ilk
 *  düzenlemede portala alınır (CRM'e yazılmaz), sonra aynı adresten açılır. */


type Tab = 'sartlar' | 'metin' | 'zeyilname' | 'odeme' | 'hakedis' | 'gecmis';

function TermsView({ d, meta }: { d: Detail; meta: Meta }) {
  const t = d.terms;
  const rates = Object.entries(t.rates);
  const rights = Object.entries(t.rights).filter(([, v]) => v).map(([k]) => meta.rights[k] ?? k);
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Panel>
        <h3 className="mb-1 text-[13px] font-extrabold">Taraflar ve kitaplar</h3>
        <dl>
          <Row label="Sözleşme türü">{meta.kinds[t.kind] ?? t.kind}</Row>
          <Row label="Yayınevi tarafı">{t.company || '—'}</Row>
          <Row label="Taraflar">
            {t.parties.length ? (
              <ul className="space-y-0.5">
                {t.parties.map((p, i) => (
                  <li key={i}>
                    {p.name} <span className="font-normal text-canvas-muted">· {meta.partyRoles[p.role] ?? p.role}{p.share != null ? ` · %${num(p.share)}` : ''}{p.viaAgent ? ' · aracılı' : ''}</span>
                  </li>
                ))}
              </ul>
            ) : '—'}
          </Row>
          <Row label="Kitaplar">
            {t.books.length ? (
              <ul className="space-y-0.5">
                {t.books.map((b, i) => (
                  <li key={i}>
                    {b.id ? <Link to={`/kitap/${b.id}`} className="text-canvas-violet hover:underline">{b.title}</Link> : b.title}{' '}
                    <span className="font-mono text-[11px] font-normal text-canvas-muted">{b.stockCode || 'stok kodu yok'}{b.listPrice ? ` · ${money(b.listPrice)}` : ''}</span>
                  </li>
                ))}
              </ul>
            ) : '—'}
          </Row>
          <Row label="Bölge / dil">{[t.territory, t.language].filter(Boolean).join(' · ') || '—'}</Row>
          <Row label="Haklar">{rights.length ? rights.join(', ') : '—'}</Row>
          {d.crm?.related && d.crm.related.length > 0 && (
            <Row label="Grup sözleşmesi">
              <ul className="space-y-0.5">
                {d.crm.related.map((r) => (
                  <li key={r.id}>
                    <Link to={`/telif-sozlesme/${r.id}`} className="text-canvas-violet hover:underline">{r.no || r.id.slice(0, 8)}</Link>{' '}
                    <span className="font-normal text-canvas-muted">
                      · {r.relation === 'ana' ? 'grup sözleşmesinin ana kaydı' : 'aynı grup sözleşmesinde'} · {meta.statuses[r.status] ?? r.status}
                      {r.start ? ` · ${day(r.start)} – ${day(r.end)}` : ''}
                    </span>
                  </li>
                ))}
              </ul>
            </Row>
          )}
        </dl>
      </Panel>
      <Panel>
        <h3 className="mb-1 text-[13px] font-extrabold">Telif ve ödeme</h3>
        <dl>
          <Row label="Ödeme şekli">{meta.paymentTypes[t.paymentType] ?? t.paymentType}</Row>
          <Row label="Telif esası">{meta.bases[t.basis] ?? t.basis}</Row>
          <Row label="Oranlar">{rates.length ? rates.map(([k, v]) => `${meta.rates[k] ?? k} %${num(v)}`).join(' · ') : '—'}</Row>
          {t.tiers.length > 0 && <Row label="Kademeler">{show('tiers', t.tiers, meta)}</Row>}
          {t.discountPct != null && <Row label="Hesaplama iskontosu">%{num(t.discountPct)}</Row>}
          <Row label="Avans">{money(t.advance, t.currency)}{t.advance ? (t.advanceRecoupable ? ' · telifden düşülür' : ' · düşülmez') : ''}</Row>
          {t.flatFee != null && <Row label="Tek ödeme">{money(t.flatFee, t.currency)}</Row>}
          {t.withholdingPct != null && <Row label="Stopaj">%{num(t.withholdingPct)}</Row>}
          <Row label="Süre">{day(t.start)} – {t.openEnded ? 'süresiz' : day(t.end)}{t.years ? ` · ${num(t.years)} yıl` : ''}</Row>
          <Row label="Hakediş">{t.periodMonths} ayda bir · vade {t.paymentDays ?? '—'} gün</Row>
          {t.printRun != null && <Row label="İlk baskı">{num(t.printRun, 0)} adet</Row>}
        </dl>
      </Panel>
      {t.notes && (
        <Panel>
          <h3 className="mb-1 text-[13px] font-extrabold">Notlar</h3>
          <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed">{t.notes}</p>
        </Panel>
      )}
    </div>
  );
}

function EditSheet({ d, meta, onClose }: { d: Detail; meta: Meta; onClose: () => void }) {
  const qc = useQueryClient();
  const [terms, setTerms] = useState<Terms>(d.terms);
  const [reason, setReason] = useState('');
  const fromDoc = useRef<{ id: string; keys: string[]; s: Suggestion } | null>(null);
  const free = !d.record || meta.freeEdit.includes(d.status);
  const changes = changedFields(d.terms, terms, meta);
  const save = useMutation({
    mutationFn: () => {
      const patch: Record<string, unknown> = {};
      for (const k of Object.keys(changes)) {
        const [g] = k.split('.');
        patch[g] = (terms as unknown as Record<string, unknown>)[g];
      }
      return contractApi.update(d.key, patch as Partial<Terms>, d.record?.version, reason || undefined);
    },
    onSuccess: (rec) => {
      toast.success('Sözleşme kaydedildi.');
      const doc = fromDoc.current;
      if (doc) {
        extractApi.accepted(doc.id, stillApplied(terms, doc.s, doc.keys), rec.id).catch(() => toast.warning('Belgeden aktarılan alanların kaydı yazılamadı; sözleşme kaydedildi.'));
      }
      qc.invalidateQueries({ queryKey: ['contracts'] });
      qc.invalidateQueries({ queryKey: ['editorial', 'contracts'] });
      onClose();
    },
  });
  const n = Object.keys(changes).length;
  return (
    <Sheet
      title={free ? 'Sözleşmeyi düzenle' : 'Kayıt düzeltmesi'}
      onClose={onClose}
      wide
      footer={
        <>
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={!n || save.isPending || (!free && !reason.trim())} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            {n ? `${n} değişikliği kaydet` : 'Değişiklik yok'}
          </button>
        </>
      }
    >
      {!d.record && <Note tone="info">Bu sözleşme CRM'den okunuyor. Kaydedince portala alınır; değişiklikler portalda tutulur, CRM'e yazılmaz.</Note>}
      {!free && (
        <div className="mb-3 space-y-2">
          <Note tone="warn">Bu sözleşme «{d.statusLabel}». Şart değişikliği zeyilnameyle yapılır. Burada yalnız kayıt hatası düzeltilir; gerekçe geçmişe yazılır.</Note>
          <Field label="Düzeltme gerekçesi">
            <input value={reason} onChange={(e) => setReason(e.target.value)} className={field} placeholder="ör. CRM'de avans yanlış girilmiş, imzalı nüshada 20.000" />
          </Field>
        </div>
      )}
      <div className="mt-2 space-y-3">
        {free && (
          <DocumentExtract
            meta={meta}
            terms={terms}
            contractKey={d.record?.id ?? d.key}
            onApply={(next, keys, id, sug) => {
              fromDoc.current = { id, keys, s: sug };
              setTerms(next);
            }}
          />
        )}
        <TermsForm value={terms} onChange={setTerms} meta={meta} />
      </div>
      {save.error && <div className="mt-3"><Note tone="err">{errMsg(save.error)}</Note></div>}
    </Sheet>
  );
}

function StatusSheet({ d, meta, to, onClose }: { d: Detail; meta: Meta; to: Status; onClose: () => void }) {
  const qc = useQueryClient();
  const [note, setNote] = useState('');
  const [signedOn, setSignedOn] = useState(d.record?.signedAt || today());
  const go = useMutation({
    mutationFn: () => contractApi.status(d.key, to, d.record?.version, note || undefined, to === 'yururlukte' ? signedOn : undefined),
    onSuccess: () => {
      toast.success(`Durum: ${meta.statuses[to]}.`);
      qc.invalidateQueries({ queryKey: ['contracts'] });
      qc.invalidateQueries({ queryKey: ['editorial', 'contracts'] });
      onClose();
    },
  });
  const needNote = to === 'feshedildi';
  return (
    <Sheet
      title={`${meta.statuses[d.status]} → ${meta.statuses[to]}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={go.isPending || (needNote && !note.trim())} onClick={() => go.mutate()}>
            {go.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Durumu değiştir
          </button>
        </>
      }
    >
      <div className="space-y-3">
        {to === 'yururlukte' && (
          <Field label="İmza tarihi">
            <input type="date" value={signedOn} onChange={(e) => setSignedOn(e.target.value)} className={field} />
          </Field>
        )}
        <Field label={needNote ? 'Fesih gerekçesi' : 'Not (isteğe bağlı)'}>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} className={field} />
        </Field>
        {to === 'yururlukte' && <Note tone="info">Yürürlüğe alındıktan sonra şartlar yalnız zeyilnameyle değişir.</Note>}
        {go.error && <Note tone="err">{errMsg(go.error)}</Note>}
      </div>
    </Sheet>
  );
}

function History({ d, meta }: { d: Detail; meta: Meta }) {
  if (!d.events.length) return <p className="py-8 text-center text-[12.5px] text-canvas-muted">{d.record ? 'Henüz kayıt yok.' : 'Sözleşme portalda düzenlenmedi; geçmiş CRM\'de.'}</p>;
  return (
    <ol className="space-y-2">
      {d.events.map((e, i) => (
        <li key={i} className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px]">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-semibold">{e.summary}</span>
            <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{stamp(e.at)} · {e.actor}</span>
          </div>
          {e.changes && e.changes.length > 0 && e.changes[0].label && (
            <ul className="mt-1.5 space-y-0.5 text-[11.5px] text-canvas-muted">
              {e.changes.map((c, j) => (
                <li key={j}>
                  <span className="font-semibold text-canvas-ink">{c.label}</span>: {show(c.field, c.old, meta, d.terms.currency)} → {show(c.field, c.new, meta, d.terms.currency)}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ol>
  );
}

export default function ContractDetail() {
  const { key = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = (params.get('sekme') as Tab) || 'sartlar';
  const setTab = (t: Tab) => setParams((p) => {
    const n = new URLSearchParams(p);
    n.set('sekme', t);
    return n;
  }, { replace: true });
  const meta = useQuery(metaOptions());
  const q = useQuery({ queryKey: detailKey(key), queryFn: () => contractApi.detail(key), enabled: !!key });
  const [edit, setEdit] = useState(false);
  const [to, setTo] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const d = q.data;
  const m = meta.data;
  const err = errMsg(q.error || meta.error, 'Sözleşme okunamadı.');

  const download = async () => {
    setBusy(true);
    try {
      const missing = await downloadDocx(`/item/${encodeURIComponent(d?.record?.id ?? key)}/document.docx`);
      if (missing.length) toast.warning(`Belgede doldurulamayan alan: ${missing.join(', ')}`);
    } catch (e) {
      toast.error(errMsg(e) ?? 'Belge indirilemedi.');
    } finally {
      setBusy(false);
    }
  };

  const transitions = d && m ? m.transitions[d.status] ?? [] : [];
  return (
    <ModuleFrame
      route="/telif-sozlesme"
      crumb="Sözleşmeler"
      title={d?.terms.title || d?.no || 'Sözleşme'}
      lead={d ? `${d.no}${d.crm ? ' · CRM kaydı' : ' · portalda açıldı'}` : 'Okunuyor…'}
      source={d?.record ? 'Portal kaydı + CRM' : 'CRM sözleşmesi'}
    >
      <div className="px-1">
        <Link to="/telif-sozlesme" className="inline-flex min-h-11 items-center gap-1 text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0">
          <ChevronLeft aria-hidden className="h-4 w-4" />
          Bütün sözleşmeler
        </Link>
      </div>
      {err && <Note tone="err">{err}</Note>}
      {(q.isLoading || meta.isLoading) && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Okunuyor…</p>}
      {d && m && (
        <>
          <Panel>
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone={statusTone(d.status)}>{d.statusLabel}</Pill>
              {d.record?.expired && <Pill tone="warn">Bitiş tarihi geçti</Pill>}
              {d.crm && <Pill tone="muted">CRM</Pill>}
              {d.record && <Pill tone="violet">Portalda düzenleniyor</Pill>}
              {d.record && <span className="text-[11.5px] text-canvas-muted">Son değişiklik {stamp(d.record.updatedAt)} · {d.record.updatedBy}</span>}
              <div className="ml-auto flex flex-wrap gap-1.5">
                {d.can.edit && d.status !== 'iptal' && (
                  <button type="button" className={btnPrimary} onClick={() => setEdit(true)}>
                    <FilePen aria-hidden className="h-4 w-4" />
                    {!d.record || m.freeEdit.includes(d.status) ? 'Düzenle' : 'Kayıt düzelt'}
                  </button>
                )}
                {d.can.edit && transitions.length > 0 && (
                  <select aria-label="Durumu değiştir" className={`${field} w-auto`} value="" onChange={(e) => e.target.value && setTo(e.target.value as Status)}>
                    <option value="">Durumu değiştir…</option>
                    {transitions.map((s) => (
                      <option key={s} value={s}>{m.statuses[s]}</option>
                    ))}
                  </select>
                )}
                {d.record && (
                  <button type="button" className={btnGhost} onClick={download} disabled={busy}>
                    {busy ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Download aria-hidden className="h-4 w-4" />}
                    Word
                  </button>
                )}
              </div>
            </div>
            {d.warnings.length > 0 && (
              <ul className="mt-3 space-y-1">
                {d.warnings.map((w) => (
                  <li key={w}><Note tone="warn">{w}</Note></li>
                ))}
              </ul>
            )}
            {d.diff.length > 0 && (
              <div className="mt-3 rounded-2xl bg-violet-50/70 p-3 text-[12px]">
                <div className="font-extrabold text-canvas-violet">CRM'e işlenmesi gereken {d.diff.length} fark</div>
                <p className="mt-0.5 text-canvas-muted">Portal CRM'e yazmaz. Bu değerler CRM kaydında elle güncellenmeli.</p>
                <ul className="mt-1.5 space-y-0.5">
                  {d.diff.map((c) => (
                    <li key={c.field}>
                      <span className="font-semibold">{c.label}</span>: CRM {show(c.field, c.old, m, d.terms.currency)} · portal {show(c.field, c.new, m, d.terms.currency)}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {d.crmError && <div className="mt-2"><Note tone="warn">{d.crmError}</Note></div>}
            {d.crmChangedSinceAdopt && <div className="mt-2"><Note tone="info">CRM kaydı portala alındıktan sonra CRM'de değiştirildi; yukarıdaki farkı kontrol edin.</Note></div>}
          </Panel>

          <Tabs
            value={tab}
            onChange={setTab}
            items={[
              { id: 'sartlar', label: 'Şartlar' },
              { id: 'metin', label: 'Metin' },
              { id: 'zeyilname', label: 'Zeyilnameler', count: d.addenda.length },
              { id: 'odeme', label: 'Ödeme takvimi', count: d.payments.filter((p) => p.status === 'planlandi').length },
              { id: 'hakedis', label: 'Hakediş', count: d.statements.filter((s) => s.status !== 'iptal').length },
              { id: 'gecmis', label: 'Geçmiş', count: d.events.length },
            ]}
          />

          {tab === 'sartlar' && <TermsView d={d} meta={m} />}
          {tab === 'metin' && <TextTab d={d} />}
          {tab === 'zeyilname' && <AddendaTab d={d} meta={m} />}
          {tab === 'odeme' && <PaymentsTab d={d} meta={m} />}
          {tab === 'hakedis' && <StatementsTab d={d} meta={m} />}
          {tab === 'hakedis' && <ContractRuns contractKey={d.record?.id ?? d.key} />}
          {tab === 'gecmis' && <Panel><History d={d} meta={m} /></Panel>}

          {edit && <EditSheet d={d} meta={m} onClose={() => setEdit(false)} />}
          {to && <StatusSheet d={d} meta={m} to={to} onClose={() => setTo(null)} />}
        </>
      )}
    </ModuleFrame>
  );
}
