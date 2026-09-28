import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { FileDown } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { fmtInt, paApi } from './api';
import { Block, PaFrame, StageBar, usePaMeta } from './parts';

/** Etki raporu: temas, hediye programı, CRM tanıtım/bağış siparişleri, projeler ve erişim; PDF. Yönetim onayı olanlar
 *  alan listesini (KVKK sınırlı) buradan yönetir. */

export default function PaReport() {
  const meta = usePaMeta();
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const rep = useQuery({ queryKey: ['pa', 'report', year], queryFn: () => paApi.report(year), enabled: ENGINE_ENABLED });
  const roles = useQuery({ queryKey: ['pa', 'crm-roles'], queryFn: paApi.crmRoles, enabled: ENGINE_ENABLED, staleTime: 10 * 60_000 });
  const r = rep.data;
  const me = meta.data?.me;
  const stageLabel = (s: string) => meta.data?.stages.find((x) => x.key === s)?.label ?? s;
  const giftLabel = (s: string) => meta.data?.giftStatus.find((x) => x.key === s)?.label ?? s;

  return (
    <PaFrame
      title="Etki raporu"
      lead="Kurul ve yönetim için tek sayfa: kaç kişiyle temas edildi, kaç kitap kime gitti ve ne döndü, CRM'deki tanıtım ve bağış siparişleri, kamu projelerinin aşaması ve erişimi."
      source={r ? `${r.year}` : 'Portal + CRM'}
      aside={
        <div className="flex flex-wrap items-center gap-2 lg:justify-end">
          <select aria-label="Yıl" value={year} onChange={(e) => setYear(Number(e.target.value))} className={`${field} w-auto`}>
            {[thisYear, thisYear - 1, thisYear - 2].map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
          {me?.canExport && (
            <a className={btnGhost} href={paApi.reportPdfUrl(year)} download>
              <FileDown aria-hidden className="h-4 w-4" />
              PDF
            </a>
          )}
        </div>
      }
    >
      {rep.error && <Note tone="err">{errText(rep.error, 'Rapor okunamadı.')}</Note>}
      {rep.isLoading && <Loading />}
      {r && (
        <>
          <KpiRow>
            <Kpi label="Kişi kartı" value={fmtInt(r.people.total)} help={`Kritik ${fmtInt(r.people.critical)} · kamu görevlisi ${fmtInt(r.people.publicOfficials)}`} info={<SqlInfo k={r.kaynaklar} alan="people" label="Kişi kartı" />} />
            <Kpi label="Temas notu" value={fmtInt(r.contacts.notes)} help={`${fmtInt(r.contacts.people)} kişi · ${fmtInt(r.contacts.orgs)} kurum`} info={<SqlInfo k={r.kaynaklar} alan="contacts" label="Temas notu" />} />
            <Kpi label="Gönderilen kitap" value={fmtInt(r.gifts.sentBooks)} help={`${fmtInt(r.gifts.sentPeople)} kişi · ${fmtInt(r.gifts.feedback)} geri dönüş`} info={<SqlInfo k={r.kaynaklar} alan="gifts" label="Gönderilen kitap" />} />
            <Kpi label="Proje erişimi" value={fmtInt(r.projects.reach.students)} help={`öğrenci · ${fmtInt(r.projects.reach.schools)} okul · ${fmtInt(r.projects.reach.books)} kitap`} info={<SqlInfo k={r.kaynaklar} alan="projects" label="Proje erişimi" />} />
          </KpiRow>
          <div className="grid gap-3 lg:grid-cols-2 lg:gap-4">
            <Block title="CRM tanıtım ve bağış siparişleri" info={<SqlInfo k={r.kaynaklar} alan="crm" label="CRM tanıtım ve bağış siparişleri" />} help="Yıl içinde CRM'de açılan siparişler; iptal ve birleştirilen siparişler sayılmaz (ayar).">
              {r.crm.error ? (
                <Note tone="warn">{r.crm.error}</Note>
              ) : r.crm.types.length === 0 ? (
                <p className="text-[12px] text-canvas-muted">Bu yıl kayıt yok.</p>
              ) : (
                <table className="w-full text-[12.5px]">
                  <thead>
                    <tr className="text-left text-[11px] uppercase tracking-wide text-canvas-muted">
                      <th className="py-1 font-bold">Tip</th>
                      <th className="py-1 text-right font-bold">Sipariş</th>
                      <th className="py-1 text-right font-bold">Kitap</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.crm.types.map((t) => (
                      <tr key={t.type} className="border-t border-slate-100">
                        <td className="py-1.5 font-semibold">{t.label}</td>
                        <td className="py-1.5 text-right font-mono tabular-nums">{fmtInt(t.orders)}</td>
                        <td className="py-1.5 text-right font-mono tabular-nums">{fmtInt(t.books)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Block>
            <Block title="Hediye programı" info={<SqlInfo k={r.kaynaklar} alan="gifts" label="Hediye programı" />} help={r.gifts.duplicates ? `Aynı kişiye aynı kitap tekrarı: ${r.gifts.duplicates}` : 'Aynı kişiye aynı kitap tekrarı yok.'}>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(r.gifts.byStatus)
                  .filter(([, n]) => n)
                  .map(([k, n]) => (
                    <Pill key={k} tone="muted">
                      {giftLabel(k)} {fmtInt(n)}
                    </Pill>
                  ))}
                {!Object.values(r.gifts.byStatus).some(Boolean) && <span className="text-[12px] text-canvas-muted">Kayıt yok.</span>}
              </div>
            </Block>
            <Block title="Kişiler alana göre" info={<SqlInfo k={r.kaynaklar} alan="people" label="Kişiler alana göre" />}>
              <ul className="space-y-1">
                {r.people.byField.map((x) => (
                  <li key={x.label} className="flex justify-between gap-2 text-[12.5px]">
                    <span>{x.label}</span>
                    <span className="font-mono tabular-nums">{fmtInt(x.count)}</span>
                  </li>
                ))}
              </ul>
            </Block>
            <Block title="Projeler" info={<SqlInfo k={r.kaynaklar} alan="projects" label="Projeler" />} help={Object.entries(r.projects.byStage).filter(([, n]) => n).map(([k, n]) => `${stageLabel(k)} ${n}`).join(' · ') || 'Proje yok.'}>
              <ul className="divide-y divide-slate-100">
                {r.projects.items.map((p) => (
                  <li key={p.id} className="py-1.5">
                    <div className="font-extrabold">{p.title}</div>
                    <div className="flex flex-wrap items-center justify-between gap-2 text-[11.5px] text-canvas-muted">
                      <StageBar stage={p.stage} label={p.stageLabel} />
                      <span>{p.orgName ?? '—'}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </Block>
            <Block title="CRM'de kişi rolleri" info={<SqlInfo k={roles.data?.kaynaklar} alan="personRoles" label="CRM kişi rolleri" />} help="Kanaat önderi diye ayrı bir rol var mı — CRM'deki roller ve kaç kişide kullanıldığı (yalnız okuma).">
              {roles.error && <Note tone="warn">{errText(roles.error, 'CRM okunamadı.')}</Note>}
              {roles.data && (
                <>
                  <p className="text-[12.5px]">
                    «Karar Veren» rolündeki etkin kişi: <b className="font-mono tabular-nums">{fmtInt(roles.data.decisionMakers)}</b>
                  </p>
                  <ul className="mt-1 flex flex-wrap gap-1">
                    {roles.data.personRoles.map((x) => (
                      <Pill key={x.id} tone="muted">
                        {x.name} {fmtInt(x.people)}
                      </Pill>
                    ))}
                  </ul>
                </>
              )}
            </Block>
            {me?.canApprove && <FieldsAdmin />}
          </div>
        </>
      )}
    </PaFrame>
  );
}

function FieldsAdmin() {
  const qc = useQueryClient();
  const meta = usePaMeta();
  const [label, setLabel] = useState('');
  const refresh = () => qc.invalidateQueries({ queryKey: ['pa', 'meta'] });
  const add = useMutation({
    mutationFn: () => paApi.addField(label),
    onSuccess: async () => {
      setLabel('');
      await refresh();
      toast.success('Alan eklendi.');
    },
    onError: (e) => toast.error(errText(e, 'Alan eklenemedi.') ?? ''),
  });
  const toggle = useMutation({
    mutationFn: ({ key, active }: { key: string; active: boolean }) => paApi.updateField(key, { active }),
    onSuccess: () => refresh(),
    onError: (e) => toast.error(errText(e, 'Güncellenemedi.') ?? ''),
  });
  return (
    <Block title="Alan listesi" help="Kişiler bu listeyle gruplanır. İnanç, mezhep, cemaat, siyasi görüş, parti, etnik köken ve sendika gibi sınıflar eklenemez (KVKK md. 6).">
      <ul className="space-y-1">
        {(meta.data?.fields ?? []).map((f) => (
          <li key={f.key} className="flex items-center justify-between gap-2 text-[12.5px]">
            <span className={f.active ? 'font-semibold' : 'text-canvas-muted line-through'}>{f.label}</span>
            <button type="button" className={`${btnGhost} !min-h-9 !py-1`} disabled={toggle.isPending} onClick={() => toggle.mutate({ key: f.key, active: !f.active })}>
              {f.active ? 'Kapat' : 'Aç'}
            </button>
          </li>
        ))}
      </ul>
      <form
        className="mt-2 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (label.trim()) add.mutate();
        }}
      >
        <input aria-label="Yeni alan" value={label} maxLength={80} onChange={(e) => setLabel(e.target.value)} placeholder="ör. Kültür ve sanat" className={field} />
        <button type="submit" className={btnPrimary} disabled={add.isPending || !label.trim()}>
          Ekle
        </button>
      </form>
    </Block>
  );
}
