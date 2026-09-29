import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Trash2 } from 'lucide-react';
import { Card, Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, fmtDate, label as labelCls, td, th } from '../admin/ui';
import { AskSheet } from '../budget/parts';
import { ENGINE_ENABLED } from '../engine';
import { MailFrame } from './parts';
import { mailApi, toRulesBody, type Ruleset } from './api';
import { ExplainLabel } from '../components/Explain';

type Editable = Pick<Ruleset, 'note' | 'categories' | 'routes' | 'sla' | 'templates'>;

const ARIA = { unit: 'birim', primary: 'sorumlu', backup: 'yedek', manager: 'birim yöneticisi', remindH: 'hatırlatma saati', escalateH: 'eskalasyon saati', topH: 'üst yönetici saati' } as const;

/** Kurallar: tür listesi, yönlendirme tablosu, SLA saatleri, yanıt şablonları. Taslak → onay → yürürlükte; taslağı yazan
 *  onaylayamaz. Yürürlükteki sürüm sınıflamada ve atamada kullanılır. */
export default function MailRules() {
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['mailbox', 'meta'], queryFn: mailApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const rules = useQuery({ queryKey: ['mailbox', 'rules'], queryFn: mailApi.rules, enabled: ENGINE_ENABLED });
  const m = meta.data;
  const r = rules.data;
  const base = r?.draft ?? r?.active ?? null;
  const [ed, setEd] = useState<Editable | null>(null);
  const [ask, setAsk] = useState<'approve' | 'discard' | null>(null);
  useEffect(() => {
    if (base) setEd(normalize(base, r?.defaultSla));
  }, [base?.version, base?.updatedAt]); // eslint-disable-line react-hooks/exhaustive-deps

  const done = (msg: string) => () => {
    toast.success(msg);
    qc.invalidateQueries({ queryKey: ['mailbox'] });
  };
  const fail = (what: string) => (e: unknown) => toast.error(errText(e, what) ?? what);
  const save = useMutation({ mutationFn: () => mailApi.saveRules(toRulesBody(ed!)), onSuccess: done('Taslak kaydedildi. Yürürlüğe girmesi için onay gerekir.'), onError: fail('Kaydedilemedi.') });
  const discard = useMutation({ mutationFn: mailApi.discardDraft, onSuccess: done('Taslak silindi.'), onError: fail('Silinemedi.') });
  const approve = useMutation({ mutationFn: (v: number) => mailApi.approveRules(v), onSuccess: done('Kurallar yürürlüğe girdi.'), onError: fail('Onaylanamadı.') });

  const canEdit = !!m?.me.canRules;
  const draft = r?.draft;
  const mineDraft = !!draft && !!m && [draft.createdBy, draft.updatedBy].includes(m.me.username);

  return (
    <MailFrame
      title="E-posta kuralları"
      lead="İleti türleri (Zeki AI yalnız bu listeden seçer), her tür için sorumlu kişi ve birim, yanıt süreleri (iş saatiyle) ve yanıt şablonları. Değişiklik önce taslak olarak kaydedilir, başka bir yetkili onaylayınca yürürlüğe girer."
      connection={m?.connection}
      lastRun={m?.lastRun}
    >
      {rules.error && <Note tone="err">{errText(rules.error, 'Kurallar okunamadı.')}</Note>}
      {rules.isLoading && <Loading />}
      {r && (
        <Card>
          <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
            {r.active && (
              <span>
                Yürürlükte: <b>sürüm {r.active.version}</b> · onaylayan {r.active.approvedBy ?? '—'} · {fmtDate(r.active.approvedAt)}
              </span>
            )}
            {draft ? <Pill tone="warn">Taslak sürüm {draft.version} · {draft.updatedBy ?? draft.createdBy}</Pill> : <Pill tone="muted">Taslak yok</Pill>}
          </div>
          {draft && m?.me.canApprove && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button type="button" className={btnPrimary} disabled={mineDraft || approve.isPending} onClick={() => setAsk('approve')}>
                Taslağı yürürlüğe al
              </button>
              {mineDraft && <span className="text-[11.5px] text-canvas-muted">Taslağı siz yazdınız; başka bir yetkili onaylamalı.</span>}
            </div>
          )}
          <p className="mt-2 text-[11.5px] text-canvas-muted">
            İş saatleri ve varsayılan süreler Yönetim → Portal ayarları → Kurumsal e-posta'dadır ({r.businessHours}). Otomatik «alındı» yanıtı bu sürümde yoktur: portal dışarıya ileti göndermez.
          </p>
        </Card>
      )}
      {ed && r && (
        <Editor ed={ed} setEd={setEd} canEdit={canEdit} roles={r.roles} />
      )}
      {ed && canEdit && (
        <div className="flex flex-wrap gap-2">
          <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>
            {draft ? 'Taslağı güncelle' : 'Taslak olarak kaydet'}
          </button>
          {draft && (
            <button type="button" className={btnGhost} disabled={discard.isPending} onClick={() => setAsk('discard')}>
              Taslağı sil
            </button>
          )}
        </div>
      )}
      {r && r.history.length > 1 && (
        <Card>
          <div className={labelCls}>Sürüm geçmişi</div>
          <ul className="mt-2 flex flex-col gap-1 text-[12px]">
            {r.history.map((h) => (
              <li key={h.version}>
                <b>Sürüm {h.version}</b> · {h.status === 'onayli' ? 'yürürlükte' : h.status === 'taslak' ? 'taslak' : 'arşiv'} · yazan {h.createdBy}
                {h.approvedBy ? ` · onaylayan ${h.approvedBy} (${fmtDate(h.approvedAt)})` : ''}
                {h.note ? ` — ${h.note}` : ''}
              </li>
            ))}
          </ul>
        </Card>
      )}
      <AskSheet
        open={ask === 'approve'}
        title="Kuralları yürürlüğe al"
        message={`Taslak sürüm ${draft?.version ?? ''} yürürlüğe girer; bundan sonra gelen iletiler bu türlerle sınıflanır ve bu tabloya göre önerilir.`}
        confirm="Yürürlüğe al"
        busy={approve.isPending}
        onClose={() => setAsk(null)}
        onConfirm={() => {
          if (draft) approve.mutate(draft.version);
          setAsk(null);
        }}
      />
      <AskSheet
        open={ask === 'discard'}
        title="Taslağı sil"
        message="Taslaktaki değişiklikler silinir; yürürlükteki kurallar değişmez."
        confirm="Sil"
        danger
        busy={discard.isPending}
        onClose={() => setAsk(null)}
        onConfirm={() => {
          discard.mutate();
          setAsk(null);
        }}
      />
    </MailFrame>
  );
}

/** Her tür için yönlendirme ve SLA satırı olsun (boş satır kaydedilmez; SLA boşsa varsayılan). */
function normalize(rs: Ruleset, def?: { remindH: number; escalateH: number; topH: number }): Editable {
  const d = def ?? { remindH: 24, escalateH: 48, topH: 72 };
  return {
    note: rs.status === 'taslak' ? rs.note : null,
    categories: rs.categories.map((c) => ({ ...c })),
    routes: rs.categories.map((c) => rs.routes.find((x) => x.category === c.key) ?? { category: c.key, unit: null, primary: null, backup: null, manager: null }),
    sla: rs.categories.map((c) => rs.sla.find((x) => x.category === c.key) ?? { category: c.key, ...d }),
    templates: rs.templates.map((t) => ({ ...t })),
  };
}

function Editor({ ed, setEd, canEdit, roles }: { ed: Editable; setEd: (e: Editable) => void; canEdit: boolean; roles: Record<string, string> }) {
  const up = (patch: Partial<Editable>) => setEd({ ...ed, ...patch });
  const addCategory = () => {
    const key = `tur-${ed.categories.length + 1}`;
    up({
      categories: [...ed.categories, { key, label: '', description: '', enabled: true, role: null, hrOnly: false, autoReply: false, sort: ed.categories.length }],
      routes: [...ed.routes, { category: key, unit: null, primary: null, backup: null, manager: null }],
      sla: [...ed.sla, { ...(ed.sla[0] ?? { remindH: 24, escalateH: 48, topH: 72 }), category: key }],
    });
  };
  const renameKey = (i: number, key: string) => {
    const old = ed.categories[i].key;
    up({
      categories: ed.categories.map((c, j) => (j === i ? { ...c, key } : c)),
      routes: ed.routes.map((x) => (x.category === old ? { ...x, category: key } : x)),
      sla: ed.sla.map((x) => (x.category === old ? { ...x, category: key } : x)),
      templates: ed.templates.map((x) => (x.category === old ? { ...x, category: key } : x)),
    });
  };
  const labelOf = (k: string) => ed.categories.find((c) => c.key === k)?.label || k;
  const dis = !canEdit;
  return (
    <>
      <Card>
        <div className="flex items-center justify-between gap-2">
          <div className="text-[13px] font-extrabold">Türler</div>
          {canEdit && (
            <button type="button" className={btnGhost} onClick={addCategory}>
              <Plus aria-hidden className="h-4 w-4" />
              Tür ekle
            </button>
          )}
        </div>
        <p className="text-[11.5px] text-canvas-muted">Açıklama Zeki AI'a gider; kısa ve ayırt edici yazın. Rol: dosya başvurusu yazar giriş sürecine aktarılır, iş başvurusunu yalnız İK görür, tanıtım/spam arşive gider.</p>
        <div className="mt-2">
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Açık</th>
                <th className={th}><ExplainLabel label="Anahtar">Türün sistemdeki kısa kodu (küçük harf, boşluksuz). Raporlar ve kurallar bu koda bağlanır; yürürlükteki bir türün kodunu değiştirmeyin.</ExplainLabel></th>
                <th className={th}>Ad</th>
                <th className={th}>Açıklama</th>
                <th className={th}>Rol</th>
              </tr>
            </thead>
            <tbody>
              {ed.categories.map((c, i) => (
                <tr key={i} className="border-t border-slate-100">
                  <td className={td}>
                    <input type="checkbox" aria-label={`${c.label} açık`} className="h-4 w-4 accent-[#7c5cff]" checked={c.enabled} disabled={dis}
                      onChange={(e) => up({ categories: ed.categories.map((x, j) => (j === i ? { ...x, enabled: e.target.checked } : x)) })} />
                  </td>
                  <td className={td}>
                    <input className={`${field} font-mono`} value={c.key} disabled={dis} aria-label="Anahtar" onChange={(e) => renameKey(i, e.target.value.toLowerCase())} />
                  </td>
                  <td className={td}>
                    <input className={field} value={c.label} disabled={dis} aria-label="Ad"
                      onChange={(e) => up({ categories: ed.categories.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)) })} />
                  </td>
                  <td className={`${td} min-w-[240px]`}>
                    <input className={field} value={c.description ?? ''} disabled={dis} aria-label="Açıklama"
                      onChange={(e) => up({ categories: ed.categories.map((x, j) => (j === i ? { ...x, description: e.target.value } : x)) })} />
                  </td>
                  <td className={td}>
                    <select className={field} value={c.role ?? ''} disabled={dis} aria-label="Rol"
                      onChange={(e) => up({ categories: ed.categories.map((x, j) => (j === i ? { ...x, role: (e.target.value || null) as typeof x.role } : x)) })}>
                      <option value="">—</option>
                      {Object.entries(roles).map(([k, v]) => (
                        <option key={k} value={k}>{v}</option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
      </Card>

      <Card>
        <div className="text-[13px] font-extrabold">Yönlendirme ve süre</div>
        <p className="text-[11.5px] text-canvas-muted">Kişileri kullanıcı adıyla yazın (şirket hesabındaki ad). Sorumlu, iletinin atanması için önerilir; hatırlatma ona, eskalasyon birim yöneticisine gider. Süreler iş saatidir: hatırlatma ≤ eskalasyon ≤ üst yönetici.</p>
        <div className="mt-2">
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Tür</th>
                <th className={th}>Birim</th>
                <th className={th}>Sorumlu</th>
                <th className={th}>Yedek</th>
                <th className={th}>Birim yöneticisi</th>
                <th className={th}><ExplainLabel label="Hatırlatma">İleti bu kadar iş saati yanıtsız kalınca sorumlu kişiye hatırlatma gider.</ExplainLabel></th>
                <th className={th}><ExplainLabel label="Eskalasyon">Bu kadar iş saati geçince durum birim yöneticisine bildirilir.</ExplainLabel></th>
                <th className={th}><ExplainLabel label="Üst">Bu kadar iş saati geçince üst yöneticiye bildirilir.</ExplainLabel></th>
              </tr>
            </thead>
            <tbody>
              {ed.routes.map((x, i) => {
                const s = ed.sla.find((y) => y.category === x.category);
                const setR = (k: 'unit' | 'primary' | 'backup' | 'manager', v: string) => up({ routes: ed.routes.map((y, j) => (j === i ? { ...y, [k]: v } : y)) });
                const setS = (k: 'remindH' | 'escalateH' | 'topH', v: string) =>
                  up({ sla: ed.sla.map((y) => (y.category === x.category ? { ...y, [k]: Number(v.replace(',', '.')) || 0 } : y)) });
                return (
                  <tr key={i} className="border-t border-slate-100">
                    <td className={`${td} font-bold`}>{labelOf(x.category)}</td>
                    {(['unit', 'primary', 'backup', 'manager'] as const).map((k) => (
                      <td key={k} className={td}>
                        <input className={field} value={x[k] ?? ''} disabled={dis} aria-label={`${labelOf(x.category)}: ${ARIA[k]}`} autoCapitalize="none" spellCheck={false} onChange={(e) => setR(k, e.target.value)} />
                      </td>
                    ))}
                    {(['remindH', 'escalateH', 'topH'] as const).map((k) => (
                      <td key={k} className={`${td} w-24`}>
                        <input className={field} inputMode="decimal" value={s ? String(s[k]) : ''} disabled={dis || !s} aria-label={`${labelOf(x.category)}: ${ARIA[k]}`} onChange={(e) => setS(k, e.target.value)} />
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </TableWrap>
        </div>
      </Card>

      <Card>
        <div className="flex items-center justify-between gap-2">
          <div className="text-[13px] font-extrabold">Yanıt şablonları</div>
          {canEdit && (
            <button type="button" className={btnGhost}
              onClick={() => up({ templates: [...ed.templates, { id: `yeni-${Date.now()}`, category: ed.categories[0]?.key ?? '', name: '', body: '' }] })}>
              <Plus aria-hidden className="h-4 w-4" />
              Şablon ekle
            </button>
          )}
        </div>
        <p className="text-[11.5px] text-canvas-muted">Zeki AI taslağı şablonu esas alır. Söz ve süre yalnız şablonda yazılıysa taslağa girer.</p>
        <div className="mt-2 flex flex-col gap-3">
          {ed.templates.length === 0 && <p className="text-[12px] text-canvas-muted">Şablon yok.</p>}
          {ed.templates.map((t, i) => {
            const setT = (patch: Partial<typeof t>) => up({ templates: ed.templates.map((y, j) => (j === i ? { ...y, ...patch } : y)) });
            return (
              <div key={t.id} className="grid gap-2 rounded-xl border border-slate-100 p-2 sm:grid-cols-[200px_1fr]">
                <div className="flex flex-col gap-2">
                  <select className={field} value={t.category} disabled={dis} aria-label="Tür" onChange={(e) => setT({ category: e.target.value })}>
                    {ed.categories.map((c) => (
                      <option key={c.key} value={c.key}>{c.label || c.key}</option>
                    ))}
                  </select>
                  <input className={field} value={t.name} disabled={dis} placeholder="Şablon adı" aria-label="Şablon adı" onChange={(e) => setT({ name: e.target.value })} />
                  {canEdit && (
                    <button type="button" className={btnGhost} onClick={() => up({ templates: ed.templates.filter((_, j) => j !== i) })}>
                      <Trash2 aria-hidden className="h-4 w-4" />
                      Kaldır
                    </button>
                  )}
                </div>
                <textarea className={`${field} min-h-[120px] font-normal`} value={t.body} disabled={dis} aria-label="Şablon metni" onChange={(e) => setT({ body: e.target.value })} />
              </div>
            );
          })}
        </div>
      </Card>

      {canEdit && (
        <Card>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Değişiklik notu</span>
            <input className={field} value={ed.note ?? ''} onChange={(e) => up({ note: e.target.value })} placeholder="Ne değişti, neden" />
          </label>
        </Card>
      )}
    </>
  );
}
