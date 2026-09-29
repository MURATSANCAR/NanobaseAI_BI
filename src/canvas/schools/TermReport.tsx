import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { schoolsApi } from './api';
import { fmtDay, fmtMoney, fmtNum, fmtPct, useSchoolsMeta } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';

/** Dönem özeti (K3): plan gerçekleşmesi, ziyaretler, il bazında penetrasyon, okul siparişleri, örnek → satış ve
 *  ziyaret edilen okulların bayisinde satış değişimi. Rakamlar SQL/kuraldan; nasıl sayıldığı her bölümde yazılı. */

function terms(current: string): string[] {
  const m = current.match(/^(\d{4})-(\d{4})\/([12])$/);
  if (!m) return [current];
  let y = Number(m[1]);
  let h = Number(m[3]);
  const out: string[] = [];
  for (let i = 0; i < 6; i += 1) {
    out.push(`${y}-${y + 1}/${h}`);
    if (h === 2) h = 1;
    else {
      h = 2;
      y -= 1;
    }
  }
  return out;
}

const termLabel = (t: string) => {
  const m = t.match(/^(\d{4})-(\d{4})\/([12])$/);
  return m ? `${m[1]}–${m[2]} ${m[3]}. dönem` : t;
};

export default function TermReport({ params, update }: { params: URLSearchParams; update: (n: Record<string, string | null>) => void }) {
  const meta = useSchoolsMeta();
  const me = meta.data?.me;
  const term = params.get('donem') || meta.data?.term || '';
  const il = params.get('il') ?? '';
  const owner = params.get('sahip') ?? '';
  const q = useQuery({
    queryKey: ['schools', 'term', term, il, owner],
    queryFn: () => schoolsApi.term(term, { il, sahip: owner }),
    enabled: ENGINE_ENABLED && !!term,
  });
  const d = q.data;
  return (
    <div className="flex flex-col gap-3">
      <section className="glass-panel grid grid-cols-1 gap-2 rounded-2xl p-3 shadow-glass-float sm:grid-cols-3 sm:rounded-3xl sm:p-4">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Dönem</span>
          <select className={field} value={term} onChange={(e) => update({ donem: e.target.value })}>
            {terms(meta.data?.term ?? term).map((t) => (
              <option key={t} value={t}>
                {termLabel(t)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>İl</span>
          <select className={field} value={il} onChange={(e) => update({ il: e.target.value || null })}>
            <option value="">Bütün iller</option>
            {(meta.data?.ils ?? []).map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </label>
        {me?.all ? (
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Temsilci kullanıcı adı</span>
            <input className={field} defaultValue={owner} key={owner} onBlur={(e) => update({ sahip: e.target.value.trim() || null })} placeholder="Örn. ayilmaz (boş: bütün ekip)" />
          </label>
        ) : (
          <p className="self-end text-[11.5px] text-canvas-muted">Plan ve ziyaret rakamları yalnız sizin kayıtlarınız.</p>
        )}
      </section>
      {q.error && <Note tone="err">{errText(q.error, 'Dönem raporu okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {d && (
        <>
          <p className="px-1 text-[12px] text-canvas-muted">
            {fmtDay(d.from)} – {fmtDay(d.to)} · veri {fmtDay(d.asOf)} okundu
          </p>
          <KpiRow>
            <Kpi label="Plan gerçekleşmesi" info={<SqlInfo k={d.kaynaklar} alan="plans" label="Plan gerçekleşmesi" />} value={fmtPct(d.plans.rate)} help={`${d.plans.realized} / ${d.plans.planned} planlı okul (${d.plans.approved} onaylı)`} explain="Dönemde plana alınan okullardan kaçına gerçekten gidildiği. Gidildi sayılması için okula portalda rapor girilmiş ya da CRM'de ziyaret tamamlanmış olmalı." />
            <Kpi label="Ziyaret" info={<SqlInfo k={d.kaynaklar} alan="visits" label="Ziyaret" />} value={fmtNum(d.visits.portal + d.visits.crm)} help={`Portal ${d.visits.portal} · CRM ${d.visits.crm} (tamamlanan)`} explain="Dönemde yapılan okul ziyaretlerinin toplamı: portalda girilen ziyaret raporları ile CRM'de tamamlanmış ziyaretler." />
            <Kpi label="Ziyaret edilen okul" info={<SqlInfo k={d.kaynaklar} alan="visits" label="Ziyaret edilen okul" />} value={fmtNum(d.visits.schools)} help="Portal ya da CRM'de dönemde en az bir ziyaret" explain="Aynı okula birden çok kez gidilse de bir sayılır." />
            <Kpi label="Okul siparişi" info={<SqlInfo k={d.kaynaklar} alan="orders" label="Okul siparişi" />} value={fmtNum(d.orders.total)} help="Örnek + okul satışı (CRM, dönemde açılan)" explain="Dönemde CRM'de okullar için açılan siparişler: örnek kitap gönderimleri ve okul satışları birlikte sayılır. Kırılımı aşağıdadır." />
          </KpiRow>

          <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
            <h2 className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
              Okul siparişleri
              <SqlInfo k={d.kaynaklar} alan="orders" label="Okul siparişleri" />
            </h2>
            <p className="mt-1 text-[11.5px] leading-snug text-canvas-muted">{d.orders.note}</p>
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
              {d.orders.items.map((o) => (
                <div key={o.type} className="rounded-xl bg-white/85 px-3 py-2">
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{o.label}</div>
                  <div className="font-mono text-[18px] font-bold tabular-nums">{fmtNum(o.count)}</div>
                  <div className="text-[11.5px] text-canvas-muted">{fmtMoney(o.amount)}</div>
                </div>
              ))}
            </div>
            <p className="mt-2 text-[12px] leading-snug">
              Örnek gönderilen {fmtNum(d.samples.schools)} okulun {fmtNum(d.samples.converted)} tanesine sonra okul satışı açıldı.{' '}
              <span className="text-canvas-muted">{d.samples.note}</span>
              <SqlInfo k={d.kaynaklar} alan="samples" label="Örnekten satışa" />
            </p>
          </section>

          <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
            <h2 className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
              Ziyaretten sonra bayide satış
              <SqlInfo k={d.kaynaklar} alan="conversion" label="Ziyaretten sonra bayide satış" />
            </h2>
            <p className="mt-1 text-[12.5px] leading-snug">
              {d.conversion.dealers
                ? `${fmtNum(d.conversion.dealers)} bayinin ${fmtNum(d.conversion.up)} tanesinde satış arttı, ${fmtNum(d.conversion.down)} tanesinde azaldı (${fmtNum(d.conversion.before)} → ${fmtNum(d.conversion.after)} adet).`
                : 'Karşılaştırılabilecek bayi yok.'}
              {d.conversion.pending ? ` ${fmtNum(d.conversion.pending)} bayide süre dolmadı.` : ''}
            </p>
            <p className="mt-1 text-[11.5px] leading-snug text-canvas-muted">{d.conversion.note}</p>
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="px-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">İl bazında ziyaret edilen okul</h2>
            <TableWrap>
              <thead>
                <tr>
                  <th className={th}>İl</th>
                  <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="byIl" label="İldeki okul">Okul</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="byIl" label="Ziyaret edilen okul">Ziyaret edilen</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="byIl" label="Ziyaret oranı">Oran</InfoLabel></th>
                </tr>
              </thead>
              <tbody>
                {d.byIl.map((r) => (
                  <tr key={r.il} className="border-t border-slate-100">
                    <td className={td}>{r.il}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtNum(r.schools)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtNum(r.visited)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(r.rate)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </section>

          {d.byOwner.length > 0 && (
            <section className="flex flex-col gap-2">
              <h2 className="px-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Temsilci</h2>
              <TableWrap>
                <thead>
                  <tr>
                    <th className={th}>Temsilci</th>
                    <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="byOwner" label="Planlı okul">Planlı</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="byOwner" label="Gidilen plan">Gidilen</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="byOwner" label="Portal raporu">Portal raporu</InfoLabel></th>
                  </tr>
                </thead>
                <tbody>
                  {d.byOwner.map((r) => (
                    <tr key={r.owner} className="border-t border-slate-100">
                      <td className={td}>{r.name}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtNum(r.planned)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtNum(r.realized)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtNum(r.visits)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            </section>
          )}
        </>
      )}
    </div>
  );
}
