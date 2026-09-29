import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { NotebookPen, UserPlus } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { HeatPill, daysAgo } from '../editorial/authors/shared';
import { fmtInt, fmtMonth, paApi, type PersonRow } from './api';
import { NoteForm, PersonForm } from './forms';
import { BASE, Block, Empty, PaFrame, StageBar, usePaMeta } from './parts';

/** M28 ilk açılış: temas zamanı gelen kişiler, açık projeler (aşama çubuğu), bu ayın hediye programı. Yalnız portal
 *  kaydından okunur; CRM beklenmez. */

export default function PaHome() {
  const navigate = useNavigate();
  const meta = usePaMeta();
  const home = useQuery({ queryKey: ['pa', 'home'], queryFn: paApi.home, enabled: ENGINE_ENABLED });
  const [noteFor, setNoteFor] = useState<PersonRow | null>(null);
  const [newPerson, setNewPerson] = useState(false);
  const h = home.data;
  const canEdit = !!meta.data?.me.canEdit;
  const st = meta.data?.settings;

  return (
    <PaFrame
      title="Kurumsal ilişkiler"
      lead="Kanaat önderleri (yazar, akademisyen, gazeteci, kamu yöneticisi gibi etkili kişiler), kurumlar ve kamu projeleri: kiminle ne zaman görüşüldü, kime hangi kitap gitti, hangi projede ne söz verildi. Kişi ve kurum bilgisi CRM'den okunur; kimseye hiçbir şey otomatik gönderilmez."
      source={h ? `${fmtInt(h.peopleCounts.toplam)} kişi kartı` : 'Portal + CRM'}
      aside={
        canEdit ? (
          <button type="button" className={`${btnPrimary} w-full lg:w-auto`} onClick={() => setNewPerson(true)}>
            <UserPlus aria-hidden className="h-4 w-4" />
            Yeni kişi
          </button>
        ) : undefined
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">Veri bağlantısı kurulu değil; bu ekran şu an veri gösteremez. Sistem yöneticinize haber verin.</Note>}
      {home.error && <Note tone="err">{errText(home.error, 'Özet okunamadı.')}</Note>}
      <KpiRow>
        <Kpi label="Temas zamanı gelen" value={h ? fmtInt(h.dueTotal) : '—'} help={st ? `Kritik ${st.criticalDays} gün, diğer ${st.contactDays} gün` : 'Son temastan bu yana'} onClick={() => navigate(`${BASE}/kisiler?kapsam=zamani`)} info={<SqlInfo k={h?.kaynaklar} alan="dueTotal" label="Temas zamanı gelen" />}
          explain={st ? `Son temasın üstünden kritik kişilerde ${st.criticalDays}, diğerlerinde ${st.contactDays} gün ya da daha fazla geçmiş kişiler; hiç temas kaydı olmayan kritik kişiler de girer. Görüştükten sonra temas notu yazın.` : 'Son temasın üstünden belirlenen süreden fazla geçmiş kişiler.'} />
        <Kpi label="Açık proje" value={h ? fmtInt(h.projects.length) : '—'} help={h ? `${fmtInt(h.lateProjects)} adımı gecikmiş · ${fmtInt(h.quietProjects)} 30 gündür hareketsiz` : 'Fikir → rapor'} onClick={() => navigate(`${BASE}/projeler`)} info={<SqlInfo k={h?.kaynaklar} alan="projects" label="Açık proje" />}
          explain="Fikir aşamasından rapora kadar süren, kapanmamış kamu projeleri (okuma kampanyası, kütüphane bağışı gibi). Alt satırda adımı geciken ve 30 gündür kayıt girilmeyenler yazar." />
        <Kpi label="Bu ay hediye" value={h ? fmtInt(h.giftBooks) : '—'} help={h ? `${fmtMonth(h.month)} · ${fmtInt(h.giftPeople)} kişi · ${fmtInt(h.waitingApproval)} onay bekliyor` : 'Aylık program'} onClick={() => navigate(`${BASE}/hediye`)} info={<SqlInfo k={h?.kaynaklar} alan="giftBooks" label="Bu ay hediye" />}
          explain="Bu ayın hediye programında kişilere gönderilmesi planlanan kitap sayısı. Her hediye onaydan geçer; öneriyi yazan kendisi onaylayamaz." />
        <Kpi label="Geciken adım" value={h ? fmtInt(h.lateSteps) : '—'} help="Tarihi geçmiş, kapanmamış sıradaki adım" info={<SqlInfo k={h?.kaynaklar} alan="lateSteps" label="Geciken adım" />}
          explain="Projelerde sıradaki adımın tarihi geçtiği hâlde kapatılmamış olanlar." />
      </KpiRow>
      {home.isLoading && <Loading />}

      {h && (
        <div className="grid gap-3 lg:grid-cols-2 lg:gap-4">
          <Block title="Temas zamanı gelen kişiler" info={<SqlInfo k={h.kaynaklar} alan="due" label="Temas zamanı gelen kişiler" />} help="En uzun süredir aranmayan ve kritik kişiler önce." action={<Link className={`${btnGhost} !min-h-9 !py-1`} to={`${BASE}/kisiler?kapsam=zamani`}>Tümü</Link>}>
            {h.due.length === 0 ? (
              <Empty title="Zamanı gelen kişi yok">Kritik kişilerle temas sınırın içinde.</Empty>
            ) : (
              <ul className="divide-y divide-slate-100">
                {h.due.slice(0, 8).map((p) => (
                  <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <Link to={`${BASE}/kisi/${p.id}`} className="min-w-0 flex-1 hover:underline">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="break-words font-extrabold">{p.name}</span>
                        {p.priority === 'kritik' && <Pill tone="warn">Kritik</Pill>}
                        <HeatPill heat={p.heat} compact />
                      </div>
                      <div className="text-[11.5px] text-canvas-muted">
                        {[p.title, p.orgName].filter(Boolean).join(' · ') || '—'} · {daysAgo(p.heat.daysSince)}
                      </div>
                    </Link>
                    {canEdit && (
                      <button type="button" className={`${btnGhost} !min-h-10 !py-1`} onClick={() => setNoteFor(p)}>
                        <NotebookPen aria-hidden className="h-3.5 w-3.5" />
                        Not yaz
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {h.due.length > 8 && <p className="mt-2 text-[11.5px] text-canvas-muted">ve {fmtInt(h.due.length - 8)} kişi daha — «Tümü».</p>}
          </Block>

          <Block title="Açık projeler" info={<SqlInfo k={h.kaynaklar} alan="projects" label="Açık projeler" />} help="Adımı gecikenler önce." action={<Link className={`${btnGhost} !min-h-9 !py-1`} to={`${BASE}/projeler`}>Pano</Link>}>
            {h.projects.length === 0 ? (
              <Empty title="Açık proje yok">Okuma kampanyası, kütüphane bağışı ya da eğitim materyali projesini «Projeler»den açın.</Empty>
            ) : (
              <ul className="divide-y divide-slate-100">
                {h.projects.slice(0, 8).map((p) => (
                  <li key={p.id} className="py-2">
                    <Link to={`${BASE}/projeler?proje=${p.id}`} className="block hover:underline">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="break-words font-extrabold">{p.title}</span>
                        {p.late && <Pill tone="err">Adım gecikti</Pill>}
                        {!p.late && p.quiet && <Pill tone="warn">30 gündür kayıt yok</Pill>}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
                        <StageBar stage={p.stage} label={p.stageLabel} />
                        <span className="text-[11.5px] text-canvas-muted">{p.orgName ?? 'Kurum seçilmedi'}</span>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            {h.projects.length > 8 && <p className="mt-2 text-[11.5px] text-canvas-muted">ve {fmtInt(h.projects.length - 8)} proje daha — «Pano».</p>}
          </Block>

          <Block title={`${fmtMonth(h.month)} hediye programı`} info={<SqlInfo k={h.kaynaklar} alan="gifts" label="Hediye programı" />} help="Bu ayın hediyelerinin onay ve sevk durumuna göre dağılımı." action={<Link className={`${btnGhost} !min-h-9 !py-1`} to={`${BASE}/hediye`}>Programı aç</Link>}>
            <dl className="grid grid-cols-3 gap-2 text-center sm:grid-cols-6">
              {(meta.data?.giftStatus ?? []).map((s) => (
                <div key={s.key} className="rounded-xl bg-white/70 px-2 py-2">
                  <dt className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{s.label}</dt>
                  <dd className="font-mono text-[18px] font-bold tabular-nums">{fmtInt(h.gifts[s.key as keyof typeof h.gifts] ?? 0)}</dd>
                </div>
              ))}
            </dl>
          </Block>
        </div>
      )}

      {noteFor && <NoteForm open onClose={() => setNoteFor(null)} target={{ personId: noteFor.id, name: noteFor.name }} />}
      <PersonForm open={newPerson} onClose={() => setNewPerson(false)} onSaved={(id) => navigate(`${BASE}/kisi/${id}`)} />
    </PaFrame>
  );
}
