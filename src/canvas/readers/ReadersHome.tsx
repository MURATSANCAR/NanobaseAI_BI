import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { Loading, Note, Pill, TableWrap, errText, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { CHANNELS, fmtDay, fmtInt, fmtPct, type Overview } from './api';
import { ConsentBar, ROOT, useMeta } from './parts';

/** Özet: tekil okur, kaynak kırılımı, kanal başına izin ve ulaşılabilir kitle, kaynak tazeliği. Yalnız sayılar. */
export default function ReadersHome({ overview, loading, error }: { overview?: Overview; loading: boolean; error: unknown }) {
  const meta = useMeta();
  if (loading) return <Loading />;
  if (error) return <Note tone="err">{errText(error, 'Özet açılamadı.')}</Note>;
  if (!overview) return null;
  const o = overview;
  if (!o.run.at) {
    return (
      <Note tone="info">
        CRM kişi, müşteri adayı ve İYS kayıtları henüz okunmadı. Gece turu her gün 03:20'de okur; «Kaynakları yeniden oku» ile hemen
        başlatılabilir (birkaç dakika sürer).
      </Note>
    );
  }
  const labels = meta.data?.channels ?? { email: 'E-posta', sms: 'SMS', call: 'Arama', kvkk: 'KVKK açık rıza' };
  const excl: Record<string, string> = meta.data?.excludeLabels ?? {};
  const st = o.run.stats;
  const campaigns = st.campaigns ?? [];
  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <KpiRow>
        <Kpi label="Tekil okur" value={fmtInt(o.readers)} help={`${fmtInt(o.records)} kaynak kaydından · ${fmtInt(o.multiSource)} okur birden çok kayıtla birleşti`} />
        <Kpi label="E-postayla ulaşılabilir" value={fmtInt(o.reach.email)} help={`İzinli${o.rules.requireKvkk ? ', KVKK rızalı' : ''}, 18 yaş üstü · okurların ${fmtPct(o.reach.email, o.readers)}'i`} />
        <Kpi label="SMS ile ulaşılabilir" value={fmtInt(o.reach.sms)} help={`Aramayla ${fmtInt(o.reach.call)} · okurların ${fmtPct(o.reach.sms, o.readers)}'i`} />
        <Kpi label="Birleştirme bekleyen" value={fmtInt(o.pendingCandidates)} help="Adı ve ili aynı, e-postası ve telefonu farklı okur çifti" />
      </KpiRow>

      {!o.rules.exportEnabled && (
        <Note tone="info">
          Liste dışa aktarımı hukuk teyidine kadar kapalı (rıza metni ve 18 yaş altı kayıtlar). Segmentler kurulur, sayılar görülür;
          liste yönetici ayarı açınca alınır.
        </Note>
      )}

      <div className="grid gap-3 lg:grid-cols-[1.2fr_1fr] lg:gap-4">
        <Panel>
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="text-[15px] font-extrabold">Kanal başına izin</h2>
            <span className="text-[11.5px] font-semibold text-canvas-muted">{fmtInt(o.readers)} okurda</span>
          </div>
          <div className="mt-3 flex flex-col gap-4">
            {CHANNELS.map((ch) => <ConsentBar key={ch} label={labels[ch]} counts={o.consent[ch]} reach={o.reach[ch]} />)}
            <ConsentBar label={labels.kvkk} counts={o.consent.kvkk} />
          </div>
          <p className="mt-3 text-[11.5px] leading-snug text-canvas-muted">
            Kural: herhangi bir kayıtta ret varsa ret; izinli yalnız {o.rules.okSources.map((s) => (s === 'iys' ? 'İYS' : s)).join(', ')} onayıyla;
            İYS kaydı olmayan kişi izinli sayılmaz.{o.rules.requireKvkk ? ' Listeye girmek için KVKK açık rızası da gerekir.' : ''}
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            {CHANNELS.map((ch) => {
              const why = Object.entries(o.notReachable[ch] ?? {}).sort((a, b) => b[1] - a[1]);
              return (
                <div key={ch} className="rounded-xl bg-slate-50 p-2.5 text-[11.5px]">
                  <div className="font-extrabold">{labels[ch]}: listeye giremeyen</div>
                  <ul className="mt-1 space-y-0.5 text-canvas-muted">
                    {why.map(([k, n]) => (
                      <li key={k} className="flex justify-between gap-2"><span>{excl[k] ?? k}</span><span className="font-mono tabular-nums">{fmtInt(n)}</span></li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </Panel>

        <div className="flex flex-col gap-3 lg:gap-4">
          <Panel>
            <h2 className="text-[15px] font-extrabold">Kaynaklar</h2>
            <ul className="mt-2 divide-y divide-slate-100 text-[12.5px]">
              {o.bySource.map((s) => (
                <li key={s.source} className="flex items-baseline justify-between gap-2 py-1.5">
                  <span className="font-bold">{s.label}</span>
                  <span className="font-mono tabular-nums text-canvas-muted">{fmtInt(s.records)} kayıt · {fmtInt(s.readers)} okur</span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
              Kopya oranı {o.duplicateRate != null ? `%${(o.duplicateRate * 100).toFixed(1)}` : '—'}. Tekil e-posta {fmtInt(o.distinctEmails)}, tekil cep
              telefonu {fmtInt(o.distinctPhones)}. Okur sayılmayan CRM kişi kartı: kurum çalışanı {fmtInt(st.excluded?.kurum)}, esere katkı veren
              (yazar, çevirmen, çizer) {fmtInt(st.excluded?.katki)}.
            </p>
          </Panel>
          <Panel>
            <h2 className="text-[15px] font-extrabold">Kaynak tazeliği</h2>
            <ul className="mt-2 divide-y divide-slate-100 text-[12.5px]">
              {o.sources.map((s) => (
                <li key={s.source} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
                  <span className="font-bold">{s.label}</span>
                  <span className="flex items-center gap-2">
                    <span className="font-mono text-[11.5px] tabular-nums text-canvas-muted">{fmtDay(s.at)}{s.rows != null ? ` · ${fmtInt(s.rows)}` : ''}</span>
                    {s.failing ? <Pill tone="err">Okunamadı</Pill> : s.stale ? <Pill tone="warn">Eski</Pill> : <Pill tone="ok">Güncel</Pill>}
                  </span>
                  {s.error && <span className="w-full text-[11.5px] text-red-700">{s.error}</span>}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[11.5px] text-canvas-muted">
              Son İYS kaydı: <strong className="text-canvas-ink">{fmtDay(st.iysLast)}</strong>
              {st.iysLast && (Date.now() - new Date(st.iysLast).getTime()) / 86_400_000 > 30 ? ' — bir aydan eski; CRM–İYS aktarımı çalışıyor mu, kontrol edilmeli.' : '.'}
            </p>
            {(st.iysUnmapped ?? 0) > 0 && (
              <p className="mt-2 text-[11.5px] text-amber-800">{fmtInt(st.iysUnmapped)} İYS kaydının kanalı belirlenemedi (Yönetim → Okur veri tabanı → İYS alanı).</p>
            )}
          </Panel>
          {st.formTypes && Object.keys(st.formTypes).length > 0 && (
            <Panel>
              <h2 className="text-[15px] font-extrabold">CRM kişi kartı: form tipi</h2>
              <p className="mt-0.5 text-[11.5px] text-canvas-muted">Bütün etkin kişi kartları (okur sayılmayanlar dahil). CRM etkinliğine katılan kişi: {fmtInt(st.eventContacts)}.</p>
              <ul className="mt-2 max-h-56 space-y-0.5 overflow-y-auto text-[12px]">
                {Object.entries(st.formTypes).sort((a, b) => b[1] - a[1]).map(([code, n]) => (
                  <li key={code} className="flex justify-between gap-2">
                    <span>{code === 'bos' ? '(boş)' : st.formTypeLabels?.[code] ?? code}</span>
                    <span className="font-mono tabular-nums text-canvas-muted">{fmtInt(n)}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          <Panel>
            <h2 className="text-[15px] font-extrabold">18 yaş altı ve ortak iletişim</h2>
            <p className="mt-1 text-[12.5px] leading-snug text-canvas-muted">
              <strong className="text-canvas-ink">{fmtInt(o.minors)}</strong> okurun bir kaydında doğum yılı 18 yaş altını gösteriyor;
              ebeveyn rızası CRM'de ayrı tutulmadığından bu okurlar hiçbir listeye girmez (hukuk teyidi bekleniyor).
              {' '}<strong className="text-canvas-ink">{fmtInt(o.sharedContact)}</strong> okurda aynı e-posta ya da telefonu taşıyan kayıtların doğum yılları
              12+ yıl ayrışıyor (ebeveyn–çocuk olabilir).
            </p>
          </Panel>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[1fr_1fr] lg:gap-4">
        <Panel>
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="text-[15px] font-extrabold">Sık işler</h2>
          </div>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            {[
              { to: `${ROOT}/segmentler/yeni`, t: 'Segment kur', d: 'Kural seç, büyüklüğü anında gör' },
              { to: `${ROOT}/yuklemeler`, t: 'Etkinlik listesi yükle', d: 'Eşleşen / yeni / izin eksik' },
              { to: `${ROOT}/birlestirme`, t: 'Birleştirme kararı', d: `${fmtInt(o.pendingCandidates)} çift bekliyor` },
            ].map((x) => (
              <Link key={x.to} to={x.to} className="rounded-xl bg-slate-50 p-3 transition-colors duration-150 hover:bg-slate-100">
                <div className="flex items-center gap-1 text-[12.5px] font-extrabold text-canvas-violet">{x.t} <ArrowRight aria-hidden className="h-3.5 w-3.5" /></div>
                <div className="mt-0.5 text-[11.5px] text-canvas-muted">{x.d}</div>
              </Link>
            ))}
          </div>
        </Panel>
        <Panel>
          <h2 className="text-[15px] font-extrabold">CRM kampanya geçmişi</h2>
          {campaigns.length === 0 ? (
            <p className="mt-1 text-[12.5px] text-canvas-muted">CRM'de e-posta/SMS kampanyası kaydı yok.</p>
          ) : (
            <div className="mt-2">
              <TableWrap>
                <thead>
                  <tr><th className={th}>Kampanya</th><th className={th}>Başlangıç</th><th className={`${th} text-right`}>Gönderim</th><th className={`${th} text-right`}>Okunma</th><th className={`${th} text-right`}>Tıklama</th></tr>
                </thead>
                <tbody>
                  {campaigns.map((c, i) => (
                    <tr key={`${c.ad}-${i}`} className="border-t border-slate-100">
                      <td className={td}>{c.ad ?? '—'}</td>
                      <td className={`${td} whitespace-nowrap`}>{fmtDay(c.baslangic)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.gonderim)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.okunma)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.tiklama)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
