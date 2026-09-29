import { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ChevronLeft, ExternalLink, Pencil, Plus, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Explain } from '../components/Explain';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { STAGE_TONE, fmtDay, fmtInt, fmtMoney, inflApi, parseNum, today, type Account, type Meta, type PersonDetail } from './api';
import CollabSheet from './CollabSheet';
import NewCollabSheet from './NewCollabSheet';
import PersonForm from './PersonForm';
import { Fact, InflFrame, RelationBadge, TopicPills, useMeta } from './parts';

/** Kişi kartı: hangi kitapları aldı, ne paylaştı, ne ödendi; hesap ölçümleri ve ilişki puanı. */
export default function PersonCard() {
  const { id = '' } = useParams();
  const meta = useMeta();
  const [params, setParams] = useSearchParams();
  const q = useQuery({ queryKey: ['influencers', 'person', id], queryFn: () => inflApi.person(id), enabled: ENGINE_ENABLED && !!id });
  const [editing, setEditing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [measure, setMeasure] = useState<Account | null>(null);
  const [topicsOpen, setTopicsOpen] = useState(false);
  const p = q.data;
  const m = meta.data;
  const open = params.get('is');
  const setOpen = (cid: string | null) => setParams(cid ? { is: cid } : {}, { replace: !cid });
  return (
    <InflFrame
      title={p?.name ?? 'İçerik üreticisi'}
      detail={p?.name}
      lead={p ? `${p.accounts.map((a) => `${a.platformAdi} @${a.handle}`).join(' · ') || 'Hesap yok'}${p.city ? ` · ${p.city}` : ''}` : 'Kişi kartı'}
      aside={p && m?.me.canEdit ? (
        <div className="flex flex-wrap gap-2 lg:justify-end">
          <button type="button" className={btnGhost} onClick={() => setEditing(true)}><Pencil aria-hidden className="h-4 w-4" /> Düzenle</button>
          {m.modelVar && <button type="button" className={btnGhost} onClick={() => setTopicsOpen(true)}><Sparkles aria-hidden className="h-4 w-4" /> Konu önerisi</button>}
          {!p.doNotContact && <button type="button" className={btnPrimary} onClick={() => setCreating(true)}><Plus aria-hidden className="h-4 w-4" /> Yeni işbirliği</button>}
        </div>
      ) : undefined}
    >
      <Link to="/isbirlikleri/kisiler" className="inline-flex min-h-11 items-center gap-1 px-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline sm:min-h-0">
        <ChevronLeft aria-hidden className="h-3.5 w-3.5" /> İçerik üreticileri
      </Link>
      {q.isLoading && <Panel><div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div></Panel>}
      {q.error && <Note tone="err">{errText(q.error, 'Kişi kartı okunamadı.')}</Note>}
      {p && m && (
        <>
          <div className="flex flex-wrap items-center gap-1.5 px-1">
            {p.doNotContact && <Pill tone="err">İletişim kurulmasın</Pill>}
            {p.minor && <Pill tone="warn">Reşit değil — veli onayı</Pill>}
            <TopicPills keys={p.topics} meta={m} />
            {p.ageGroups.map((a) => <Pill key={a} tone="muted">{m.yasGruplari[a] ?? a}</Pill>)}
          </div>
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-6">
            <Fact label="İşbirliği" value={fmtInt(p.totals.collabs)} help={`${p.totals.published} yayında`} info={<SqlInfo k={p.kaynaklar} alan="totals" label="İşbirliği" />} />
            <Fact label="Etkileşim" value={fmtInt(p.totals.engagement)} info={<SqlInfo k={p.kaynaklar} alan="totals" label="Etkileşim" />} />
            <Fact label="Harcama" value={p.totals.spend !== null ? fmtMoney(p.totals.spend) : 'yetkiyle görünür'} info={<SqlInfo k={p.kaynaklar} alan="totals" label="Harcama" />} />
            <Fact label="Etkileşim başı maliyet" value={p.totals.cpe !== null ? fmtMoney(p.totals.cpe) : '—'} info={<><SqlInfo k={p.kaynaklar} alan="totals" label="Etkileşim başı maliyet" /><Explain label="Etkileşim başı maliyet">Bu kişiye yapılan harcamanın, paylaşımlarının aldığı etkileşime (beğeni, yorum, paylaşım, kaydetme) bölümü.</Explain></>} />
            <Fact label="Ücret aralığı" value={m.me.canSeeFee ? (p.feeMin !== null || p.feeMax !== null ? `${fmtMoney(p.feeMin)} – ${fmtMoney(p.feeMax)}` : '—') : p.feeSet ? 'girildi' : '—'} />
            <Fact label="İlişki puanı" info={<><SqlInfo k={p.kaynaklar} alan="relation" label="İlişki puanı" /><Explain label="İlişki puanı">0–100 arası puan: paylaşımla sonuçlanan son işbirliğinin yakınlığı (en çok 40), son 12 aydaki işbirliği sayısı (en çok 30) ve vazgeçilmeden sonuçlanan işlerin oranı (en çok 30). 67 ve üstü sıcak, 33 ve altı soğuk ilişkidir.</Explain></>} value={<RelationBadge rel={p.relation} />} help={p.relation.last ? `son yayın ${fmtDay(p.relation.last)}` : undefined} />
          </div>
          <Panel>
            <h2 className="mb-2 flex items-center gap-1 text-[13px] font-extrabold">Hesaplar ve ölçümler<SqlInfo k={p.kaynaklar} alan="accounts" label="Hesaplar ve ölçümler" /></h2>
            {p.jumps.length > 0 && (
              <Note tone="warn">
                Takipçi sıçraması (kendi ölçümlerimiz): {p.jumps.map((j) => `${fmtDay(j.from)} → ${fmtDay(j.to)} %${j.pct}`).join(' · ')}. Sahte takipçi puanı değildir; hesabı elle inceleyin.
              </Note>
            )}
            <div className="flex flex-col gap-2">
              {p.accounts.length === 0 && <div className="text-[12.5px] text-canvas-muted">Hesap girilmemiş.</div>}
              {p.accounts.map((a) => (
                <div key={a.id} className="flex flex-wrap items-center gap-2 rounded-xl bg-white/80 px-3 py-2">
                  <span className="min-w-0 flex-1 break-words text-[13px] font-bold">{a.platformAdi} @{a.handle}</span>
                  {a.url && <a href={a.url} target="_blank" rel="noreferrer" className="text-canvas-violet" aria-label="Hesabı aç"><ExternalLink aria-hidden className="h-4 w-4" /></a>}
                  <span className="font-mono text-[12px] tabular-nums">{a.latest?.followers !== null && a.latest?.followers !== undefined ? `${fmtInt(a.latest.followers)} takipçi` : 'ölçüm yok'}</span>
                  {a.latest && <span className="text-[11px] text-canvas-muted">{fmtDay(a.latest.day)} · {a.latest.source === 'api' ? 'otomatik' : 'elle'}</span>}
                  {m.me.canEdit && <button type="button" className={btnGhost} onClick={() => setMeasure(a)}>Ölçüm gir</button>}
                </div>
              ))}
            </div>
          </Panel>
          <Panel>
            <h2 className="mb-2 flex items-center gap-1 text-[13px] font-extrabold">İşbirlikleri<SqlInfo k={p.kaynaklar} alan="collabs" label="İşbirlikleri" /></h2>
            {p.collabs.length === 0 ? <div className="text-[12.5px] text-canvas-muted">Bu kişiyle henüz işbirliği yok. «Yeni işbirliği» ile başlayabilirsiniz.</div> : (
              <TableWrap>
                <table className="w-full min-w-[720px] text-[12.5px]">
                  <thead><tr><th className={th}>No</th><th className={th}>Kitap</th><th className={th}>Tür</th><th className={th}>Aşama</th><th className={th}>Yayın</th><th className={th}>Etkileşim</th>{m.me.canSeeFee && <th className={th}>Ücret</th>}<th className={th}>Ödeme</th></tr></thead>
                  <tbody>
                    {p.collabs.map((c) => (
                      <tr key={c.id} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50" onClick={() => setOpen(c.id)}>
                        <td className={`${td} font-mono`}>{c.code}</td>
                        <td className={td}>{c.bookTitle}</td>
                        <td className={td}>{c.kindLabel}</td>
                        <td className={td}><Pill tone={STAGE_TONE[c.stage]}>{c.stageLabel}</Pill></td>
                        <td className={td}>{c.publishedUrl ? <a href={c.publishedUrl} target="_blank" rel="noreferrer" className="text-canvas-violet hover:underline" onClick={(e) => e.stopPropagation()}>{fmtDay(c.publishedAt)}</a> : fmtDay(c.duePublish)}</td>
                        <td className={`${td} font-mono tabular-nums`}>{fmtInt(c.engagement)}</td>
                        {m.me.canSeeFee && <td className={`${td} font-mono tabular-nums`}>{fmtMoney(c.fee)}</td>}
                        <td className={td}>{c.payout ? c.payout.statusLabel : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            )}
          </Panel>
          <CrmOrders p={p} />
          {p.notes && <Panel><h2 className="mb-1 text-[13px] font-extrabold">Not</h2><p className="whitespace-pre-wrap text-[12.5px]">{p.notes}</p></Panel>}
          <CollabSheet id={open} meta={m} onClose={() => setOpen(null)} />
          <PersonForm open={editing} meta={m} person={p} onClose={() => setEditing(false)} />
          <NewCollabSheet open={creating} meta={m} person={{ id: p.id, name: p.name }} onClose={() => setCreating(false)} onCreated={setOpen} />
          <MeasureSheet account={measure} onClose={() => setMeasure(null)} personId={p.id} />
          <TopicSheet open={topicsOpen} p={p} meta={m} onClose={() => setTopicsOpen(false)} />
        </>
      )}
    </InflFrame>
  );
}

function CrmOrders({ p }: { p: PersonDetail }) {
  if (!p.orderNos.length) return null;
  const o = p.crmOrders;
  return (
    <Panel>
      <h2 className="mb-1 flex items-center gap-1 text-[13px] font-extrabold">Tanıtım gönderimi (CRM)<SqlInfo k={p.kaynaklar} alan="crmOrders" label="Tanıtım gönderimi" /></h2>
      <p className="mb-2 text-[11.5px] text-canvas-muted">İşbirliklerine yazılan «Pazarlama (Tanıtım Gönderimi)» sipariş numaralarından, yalnız okuma.</p>
      {o === null ? null : 'hata' in o ? <Note tone="warn">CRM okunamadı: {o.hata}</Note> : (
        <div className="flex flex-col gap-1 text-[12.5px]">
          <div className="font-bold">{fmtInt(o.toplamAdet)} kitap · {o.siparisler.length} sipariş</div>
          {o.siparisler.map((s) => <div key={s.siparisNo} className="font-mono text-[12px]">{s.siparisNo} · {fmtDay(s.tarih)} · {fmtInt(s.adet)} adet</div>)}
          {o.bulunamayan.length > 0 && <div className="text-[11.5px] text-amber-700">CRM'de tanıtım siparişi olarak bulunamadı: {o.bulunamayan.join(', ')}</div>}
        </div>
      )}
    </Panel>
  );
}

function MeasureSheet({ account, personId, onClose }: { account: Account | null; personId: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [day, setDay] = useState(today());
  const [f, setF] = useState({ followers: '', posts: '', avgLikes: '', avgComments: '' });
  const num = (s: string) => (s.trim() ? parseNum(s) : null);
  const save = useMutation({
    mutationFn: () => inflApi.addSnapshot(account!.id, { day, followers: num(f.followers), posts: num(f.posts), avgLikes: num(f.avgLikes), avgComments: num(f.avgComments) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['influencers', 'person', personId] });
      toast.success('Ölçüm kaydedildi.');
      setF({ followers: '', posts: '', avgLikes: '', avgComments: '' });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const inp = (k: keyof typeof f, lbl: string) => (
    <label className="flex flex-col gap-1">
      <span className={labelCls}>{lbl}</span>
      <input className={`${field} font-mono`} inputMode="numeric" value={f[k]} onChange={(e) => setF((x) => ({ ...x, [k]: e.target.value }))} />
    </label>
  );
  return (
    <Sheet open={!!account} modal onClose={onClose} title={account ? `${account.platformAdi} @${account.handle}` : 'Ölçüm'}
      subtitle="Hesabın herkese açık sayıları; aynı güne ikinci giriş öncekinin yerine geçer.">
      <div className="flex flex-col gap-3 text-[13px]">
        <label className="flex flex-col gap-1"><span className={labelCls}>Gün</span><input type="date" className={field} value={day} max={today()} onChange={(e) => setDay(e.target.value)} /></label>
        <div className="grid grid-cols-2 gap-3">
          {inp('followers', 'Takipçi')}
          {inp('posts', 'Gönderi')}
          {inp('avgLikes', 'Ort. beğeni')}
          {inp('avgComments', 'Ort. yorum')}
        </div>
        <div className="flex justify-end"><button type="button" className={btnPrimary} disabled={save.isPending || Object.values(f).every((v) => !v.trim())} onClick={() => save.mutate()}>Kaydet</button></div>
      </div>
    </Sheet>
  );
}

function TopicSheet({ open, p, meta, onClose }: { open: boolean; p: PersonDetail; meta: Meta; onClose: () => void }) {
  const qc = useQueryClient();
  const [text, setText] = useState('');
  const ask = useMutation({ mutationFn: () => inflApi.suggestTopics(p.id, text), onError: (e) => toast.error(errText(e, 'Öneri alınamadı.') ?? '') });
  const apply = useMutation({
    mutationFn: (k: string) => inflApi.updatePerson(p.id, { topics: [...new Set([...p.topics, k])] }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['influencers'] }); toast.success('Konu eklendi.'); onClose(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const r = ask.data;
  return (
    <Sheet open={open} modal onClose={onClose} title="Konu önerisi" subtitle="Biyografiyi ya da son gönderi başlıklarını yapıştırın; Zeki AI kapalı listeden bir konu önerir, siz onaylarsınız.">
      <div className="flex flex-col gap-3 text-[13px]">
        <textarea className={`${field} min-h-[120px]`} value={text} onChange={(e) => setText(e.target.value)} />
        <div className="flex justify-end"><button type="button" className={btnGhost} disabled={text.trim().length < 20 || ask.isPending} onClick={() => ask.mutate()}>Öner</button></div>
        {r && (
          r.topic ? (
            <div className="flex flex-wrap items-center gap-2 rounded-xl bg-slate-50 p-3">
              <span className="font-bold">{meta.konular[r.topic]}</span>
              <span className="font-mono text-[12px] text-canvas-muted">{r.probability !== null ? `%${Math.round(r.probability * 100)}` : 'olasılık yok'}</span>
              {!r.confident && <Pill tone="warn">Emin değil</Pill>}
              <button type="button" className={btnPrimary} disabled={apply.isPending || p.topics.includes(r.topic)} onClick={() => apply.mutate(r.topic as string)}>
                {p.topics.includes(r.topic) ? 'Zaten var' : 'Konulara ekle'}
              </button>
            </div>
          ) : <Note tone="info">Konu önerilemedi.</Note>
        )}
      </div>
    </Sheet>
  );
}
