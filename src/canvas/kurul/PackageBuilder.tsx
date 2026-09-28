import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Download, Loader2, Lock, Send, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { fmtDay, fmtTime, kurulApi, waitJob, type KurulMeta, type Package } from './api';
import { AskSheet, ColorBadge, Empty, KurulFrame } from './parts';

/** Kurul paketi: derlenen anlık görüntü → yönetici özeti (Zeki AI taslağı, genel müdür düzeltir ve onaylar) → dondur (PDF,
 *  sha256) → dağıtım kaydı. Dondurulan paket değişmez; kurul üyesi yalnız dondurulmuş paketi görür. */
export default function PackageBuilder() {
  const { id = '' } = useParams();
  const meta = useQuery({ queryKey: ['kurul', 'meta'], queryFn: kurulApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({
    queryKey: ['kurul', 'package', id],
    queryFn: () => kurulApi.pkg(id),
    enabled: ENGINE_ENABLED && !!id,
    refetchInterval: (query) => (query.state.data?.ozetDurum === 'hazirlaniyor' ? 4000 : false),
  });
  const p = q.data;
  const top = p?.icerik.kapak.toplanti;
  return (
    <KurulFrame
      title={p ? `Kurul paketi · sürüm ${p.surum}` : 'Kurul paketi'}
      lead={top ? `${top.baslik} · ${fmtDay(top.tarih)} · gösterge dönemi ${p?.icerik.kapak.donemAdi}` : 'Paket okunuyor…'}
      back={{ to: p ? `/kurul/toplanti/${p.toplantiId}` : '/kurul?sekme=paketler', label: 'Toplantı' }}
    >
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Paket okunamadı.')}</Note>}
      {p && meta.data && (
        <>
          <StatusBar p={p} meta={meta.data} />
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)] lg:gap-4">
            <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
              <SummaryPanel p={p} meta={meta.data} />
              <ContentView p={p} />
            </div>
            <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
              {p.durum !== 'taslak' && (meta.data.me.canFreeze) && <DistributePanel p={p} />}
              {p.dagitim.length > 0 && (
                <Panel>
                  <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Dağıtım kaydı</h2>
                  <ul className="flex flex-col gap-1 text-[12px]">
                    {p.dagitim.map((d) => (
                      <li key={d.id} className="rounded-lg bg-white/80 px-2 py-1.5">
                        <span className="font-bold">{d.alici}</span> · {d.kanalAdi}
                        <span className="block text-[11px] text-canvas-muted">{d.gonderen} · {fmtTime(d.zaman)}{d.sonuc ? ` · ${d.sonuc}` : ''}</span>
                      </li>
                    ))}
                  </ul>
                </Panel>
              )}
            </div>
          </div>
        </>
      )}
    </KurulFrame>
  );
}

function StatusBar({ p, meta }: { p: Package; meta: KurulMeta }) {
  const qc = useQueryClient();
  const [asking, setAsking] = useState(false);
  const freeze = useMutation({
    mutationFn: () => kurulApi.freeze(p.id),
    onSuccess: () => {
      toast.success('Paket donduruldu; PDF hazır.');
      setAsking(false);
      qc.invalidateQueries({ queryKey: ['kurul'] });
    },
    onError: (e) => toast.error(errText(e, 'Paket dondurulamadı.')),
  });
  const draft = p.durum === 'taslak';
  const missing = p.icerik.eksikYorum;
  return (
    <Panel>
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-canvas-muted">
          <Pill tone={draft ? 'warn' : 'ok'}>{p.durumAdi}</Pill>
          <span>derleyen {p.derleyen} · {fmtTime(p.derleme)}</span>
          {p.dondurma && <span>· donduran {p.donduran} · {fmtTime(p.dondurma)}</span>}
          <span className="font-mono">· içerik {p.icerikSha256.slice(0, 12)}</span>
          {p.pdfSha256 && <span className="font-mono">· PDF {p.pdfSha256.slice(0, 12)}</span>}
        </div>
        <div className="flex flex-wrap gap-2">
          {!draft && p.pdfVar && meta.me.canExport && (
            <a className={btnPrimary} href={kurulApi.pdfUrl(p.id)}><Download aria-hidden className="h-4 w-4" /> PDF indir</a>
          )}
          {draft && meta.me.canFreeze && (
            <button type="button" className={btnPrimary} disabled={p.ozetDurum === 'taslak' || p.ozetDurum === 'hazirlaniyor'} onClick={() => setAsking(true)}>
              <Lock aria-hidden className="h-4 w-4" /> Dondur
            </button>
          )}
        </div>
      </div>
      {draft && p.ozetDurum === 'taslak' && meta.me.canFreeze && <p className="mt-2 text-[11.5px] text-canvas-muted">Dondurmadan önce yönetici özetini onaylayın ya da boşaltın.</p>}
      {draft && missing.length > 0 && (
        <Note tone="warn">
          Yorumu olmayan {missing.length} renkli gösterge
          <SqlInfo k={p.kaynaklar} alan="icerik.eksikYorum" label="Yorumu olmayan renkli gösterge" className="ml-0.5" />: {missing.map((m) => `${m.ad}${m.sahip ? ` (${m.sahip})` : ''}`).join(', ')}. Yorum gelince yeniden derleyin.
        </Note>
      )}
      {!draft && <p className="mt-2 text-[11.5px] text-canvas-muted">Dondurulan paket değişmez; kaynak rakamlar sonradan değişse de bu sürüm aynı kalır. Düzeltme için toplantı sayfasından yeniden derleyin (yeni sürüm).</p>}
      <AskSheet open={asking} title="Paketi dondur" confirm="Dondur" busy={freeze.isPending} onClose={() => setAsking(false)} onConfirm={() => freeze.mutate()}
        message="Dondurulan paket ve PDF'i bir daha değişmez; kurul üyeleri bu sürümü görür. Devam edilsin mi?" />
    </Panel>
  );
}

function SummaryPanel({ p, meta }: { p: Package; meta: KurulMeta }) {
  const qc = useQueryClient();
  const draft = p.durum === 'taslak';
  const [text, setText] = useState(p.ozetMetin ?? '');
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [foreign, setForeign] = useState<string[]>([]);
  const [foreignK, setForeignK] = useState<Kaynaklar | undefined>(undefined);
  const refresh = () => qc.invalidateQueries({ queryKey: ['kurul', 'package', p.id] });
  const save = useMutation({
    mutationFn: () => kurulApi.editSummary(p.id, text),
    onSuccess: (out) => {
      setForeign(out.olguDisiSayilar ?? []);
      setForeignK(out.kaynaklar);
      setEditing(false);
      toast.success('Özet kaydedildi; onay bekliyor.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Özet kaydedilemedi.')),
  });
  const approve = useMutation({
    mutationFn: () => kurulApi.approveSummary(p.id),
    onSuccess: () => {
      toast.success('Yönetici özeti onaylandı.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Özet onaylanamadı.')),
  });
  async function ask() {
    setBusy(true);
    try {
      const j = await kurulApi.draftSummary(p.id);
      const done = await waitJob(j.id);
      if (done.durum === 'hata') toast.error(done.hata || 'Taslak hazırlanamadı.');
      else toast.success('Zeki AI taslağı hazır.');
    } catch (e) {
      toast.error(errText(e, 'Taslak istenemedi.'));
    } finally {
      setBusy(false);
      refresh();
    }
  }
  const canAsk = draft && meta.modelVar && (meta.me.canPrepare || meta.me.canFreeze);
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">
          Yönetici özeti {p.ozetMetin && <SqlInfo k={p.kaynaklar} alan="ozetMetin" label="Yönetici özetinin olguları" />}
        </h2>
        <span className="flex flex-wrap items-center gap-1.5">
          <Pill tone={p.ozetDurum === 'onayli' ? 'ok' : p.ozetDurum === 'hata' ? 'err' : p.ozetDurum === 'yok' ? 'muted' : 'warn'}>{p.ozetDurumAdi}</Pill>
          {p.ozetKaynak && <Pill tone="violet">{p.ozetKaynak === 'zeki' ? 'Zeki AI taslağı' : 'Elle yazıldı'}</Pill>}
        </span>
      </div>
      {p.ozetDurum === 'hazirlaniyor' && <p className="inline-flex items-center gap-1.5 text-[12px] text-canvas-muted"><Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" /> Zeki AI yazıyor…</p>}
      {p.ozetDurum === 'hata' && p.ozetNot && <Note tone="err">{p.ozetNot}</Note>}
      {editing ? (
        <div className="flex flex-col gap-2">
          <textarea aria-label="Yönetici özeti" className={`${field} min-h-[240px]`} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="flex justify-end gap-2">
            <button type="button" className={btnGhost} onClick={() => { setText(p.ozetMetin ?? ''); setEditing(false); }}>Vazgeç</button>
            <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>Kaydet</button>
          </div>
        </div>
      ) : p.ozetMetin ? (
        <div className="whitespace-pre-wrap break-words rounded-xl bg-white/80 p-3 text-[13px] leading-relaxed">{p.ozetMetin}</div>
      ) : (
        p.ozetDurum !== 'hazirlaniyor' && <Empty>Özet yok.{draft ? ' Zeki AI taslağı isteyin ya da elle yazın.' : ''}</Empty>
      )}
      {foreign.length > 0 && (
        <Note tone="warn">
          Metinde paket olgularında olmayan sayı var: {foreign.join(', ')}
          <SqlInfo k={foreignK ?? p.kaynaklar} alan="olguDisiSayilar" label="Olgu dışı sayılar" className="ml-0.5" />. Onaylamadan önce kontrol edin.
        </Note>
      )}
      {p.ozetOnaylayan && <p className="mt-1 text-[11.5px] text-canvas-muted">Onaylayan {p.ozetOnaylayan} · {fmtTime(p.ozetOnay)}</p>}
      {draft && !editing && (
        <div className="mt-2 flex flex-wrap gap-2">
          {canAsk && (
            <button type="button" className={btnGhost} disabled={busy || p.ozetDurum === 'hazirlaniyor'} onClick={ask}>
              {busy ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />} Zeki AI taslağı
            </button>
          )}
          {meta.me.canFreeze && <button type="button" className={btnGhost} onClick={() => { setText(p.ozetMetin ?? ''); setEditing(true); }}>Düzelt</button>}
          {meta.me.canFreeze && p.ozetDurum === 'taslak' && (
            <button type="button" className={btnPrimary} disabled={approve.isPending} onClick={() => approve.mutate()}><Check aria-hidden className="h-4 w-4" /> Onayla</button>
          )}
        </div>
      )}
      {canAsk && <p className="mt-1 text-[11px] text-canvas-muted">Zeki AI yalnız bu paketin olgularını görür; olgularda olmayan sayı yazarsa taslak kaydedilmez.</p>}
    </Panel>
  );
}

function DistributePanel({ p }: { p: Package }) {
  const qc = useQueryClient();
  const members = useQuery({ queryKey: ['kurul', 'members'], queryFn: kurulApi.members, enabled: ENGINE_ENABLED });
  const [picked, setPicked] = useState<string[]>([]);
  const go = useMutation({
    mutationFn: () => kurulApi.distribute(p.id, picked),
    onSuccess: () => {
      toast.success('Dağıtım kaydedildi. Hesabı olmayan üyeye PDF\'i siz iletin.');
      setPicked([]);
      qc.invalidateQueries({ queryKey: ['kurul', 'package', p.id] });
    },
    onError: (e) => toast.error(errText(e, 'Dağıtım kaydedilemedi.')),
  });
  const items = (members.data?.items ?? []).filter((m) => m.aktif);
  return (
    <Panel>
      <h2 className="mb-1 text-[15px] font-extrabold tracking-tight">Dağıtım</h2>
      <p className="mb-2 text-[11.5px] text-canvas-muted">Portal kimseye e-posta göndermez. Hesabı olan üye paketi portaldan açar; olmayana PDF'i siz iletirsiniz. Burada kime gittiği kaydedilir.</p>
      {members.isLoading && <Loading />}
      {items.length === 0 && !members.isLoading && <Empty>Kurul üyesi kaydı yok (Kurul › Kurul üyeleri).</Empty>}
      <ul className="flex flex-col gap-1">
        {items.map((m) => (
          <li key={m.id}>
            <label className="flex min-h-11 items-center gap-2 rounded-lg bg-white/80 px-2 py-1.5 text-[12.5px]">
              <input type="checkbox" className="h-4 w-4" checked={picked.includes(m.id)}
                onChange={(e) => setPicked(e.target.checked ? [...picked, m.id] : picked.filter((x) => x !== m.id))} />
              <span className="min-w-0">
                <span className="block font-bold">{m.ad}</span>
                <span className="block text-[11px] text-canvas-muted">{m.kurulAdi} · {m.adHesabi ? 'portal bağlantısı' : 'PDF elle iletilecek'}</span>
              </span>
            </label>
          </li>
        ))}
      </ul>
      {items.length > 0 && (
        <button type="button" className={`${btnPrimary} mt-2`} disabled={!picked.length || go.isPending} onClick={() => go.mutate()}>
          <Send aria-hidden className="h-4 w-4" /> Dağıtımı kaydet
        </button>
      )}
    </Panel>
  );
}

function ContentView({ p }: { p: Package }) {
  const c = p.icerik;
  const ends = Object.entries(c.kapak.veriSonGunleri ?? {});
  return (
    <>
      <Panel>
        <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Kapak</h2>
        <dl className="grid grid-cols-1 gap-x-4 gap-y-1.5 text-[12.5px] sm:grid-cols-2">
          <div><dt className={labelCls}>Toplantı</dt><dd>{c.kapak.toplanti.baslik} · {fmtDay(c.kapak.toplanti.tarih)}</dd></div>
          <div><dt className={labelCls}>Gösterge dönemi</dt><dd>{c.kapak.donemAdi}</dd></div>
          <div className="sm:col-span-2"><dt className={labelCls}>Durum</dt>
            <dd>
              {c.sayilar.toplam} göstergeden {c.sayilar.hazir} hazır, {c.sayilar.gri} kaynak yok; {c.sayilar.kirmizi} dikkat, {c.sayilar.sari} izlenmeli.
              <SqlInfo k={p.kaynaklar} alan="icerik.sayilar" label="Gösterge sayıları" className="ml-0.5" />
              {' '}Açık kurul aksiyonu {c.aksiyonOzeti.acik}, geciken {c.aksiyonOzeti.geciken}.
              <SqlInfo k={p.kaynaklar} alan="icerik.aksiyonOzeti" label="Kurul aksiyonları" className="ml-0.5" />
            </dd>
          </div>
          {ends.length > 0 && (
            <div className="sm:col-span-2"><dt className={labelCls}>Verinin son günü</dt>
              <dd className="flex flex-col">{ends.map(([k, v]) => <span key={k}>{k}: {fmtDay(v)}</span>)}</dd>
            </div>
          )}
        </dl>
      </Panel>
      <Panel>
        <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Gösterge tablosu</h2>
        <div className="flex flex-col gap-3">
          {c.gostergeler.map((b) => (
            <section key={b.id}>
              <h3 className="mb-1 text-[13px] font-extrabold">{b.ad}</h3>
              <ul className="flex flex-col gap-1">
                {b.gostergeler.map((g) => (
                  <li key={g.kod} className="rounded-lg bg-white/80 px-2.5 py-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="min-w-0 break-words text-[12.5px] font-bold">{g.ad}</span>
                      <span className="flex items-center gap-2">
                        {g.durum === 'ok' && <span className="font-mono text-[12.5px] font-bold tabular-nums">{g.degerMetin}</span>}
                        <ColorBadge durum={g.durum} renk={g.renk} />
                        <SqlInfo k={p.kaynaklar} alan="icerik.gostergeler[].gostergeler[]" row={g.kod} label={g.ad} />
                      </span>
                    </div>
                    <p className="text-[11px] text-canvas-muted">
                      {[g.oncekiMetin ? `Önceki ${g.oncekiMetin}${g.oncekiEtiket ? ` (${g.oncekiEtiket})` : ''}` : null,
                        g.hedefMetin ? `Hedef ${g.hedefMetin}` : null, g.veriSonGunu ? `Veri ${fmtDay(g.veriSonGunu)}` : null,
                        g.durum !== 'ok' ? g.not : null].filter(Boolean).join(' · ')}
                    </p>
                    {g.yorum && <p className="mt-0.5 text-[12px]"><b>Yorum ({g.yorum.onaylayan ?? g.yorum.yazan}):</b> {g.yorum.metin}</p>}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </Panel>
      <Panel>
        <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Önceki kararların durumu</h2>
        {c.oncekiKararlar.length === 0 ? <Empty>Önceki toplantılardan izlenen karar yok.</Empty> : (
          <ul className="flex flex-col gap-2">
            {c.oncekiKararlar.map((d, i) => (
              <li key={i} className="rounded-lg bg-white/80 px-2.5 py-2 text-[12.5px]">
                <div className="text-[11px] text-canvas-muted">{fmtDay(d.tarih)} · {d.toplanti}</div>
                <p className="font-bold">{d.karar}</p>
                {d.aksiyonlar.map((a, j) => (
                  <p key={j} className={`text-[11.5px] ${a.gecikti ? 'font-bold text-red-700' : 'text-canvas-muted'}`}>
                    • {a.eylem} — {a.sahip ?? 'sahip yok'}, {fmtDay(a.termin)}: {a.durum}{a.sonNot ? ` (${a.sonNot})` : ''}
                  </p>
                ))}
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <Panel>
        <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Gündem</h2>
        {c.gundem.length === 0 ? <Empty>Gündem girilmedi.</Empty> : (
          <ol className="flex flex-col gap-1 text-[12.5px]">
            {c.gundem.map((g, i) => <li key={i}><b>{g.sira ?? i + 1}.</b> {g.baslik} <span className="text-canvas-muted">({g.turAdi ?? g.tur}{g.sunan ? ` · ${g.sunan}` : ''})</span></li>)}
          </ol>
        )}
      </Panel>
      <Panel>
        <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold tracking-tight">
          Risk brifingi {c.risk.brifing?.metin && <SqlInfo k={p.kaynaklar} alan="icerik.risk.brifing" label="Risk brifinginin dayandığı kayıt" />}
        </h2>
        {c.risk.brifing?.metin ? (
          <>
            <p className="mb-1 text-[11px] text-canvas-muted">Dönem {c.risk.brifing.donem} · onaylayan {c.risk.brifing.onaylayan ?? '—'}</p>
            <div className="whitespace-pre-wrap break-words text-[12.5px] leading-relaxed">{c.risk.brifing.metin}</div>
          </>
        ) : <Empty>Onaylı risk brifingi yok.</Empty>}
      </Panel>
      <Panel>
        <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold tracking-tight">
          Pazar ve rekabet özeti {c.pazar?.metin && <SqlInfo k={p.kaynaklar} alan="icerik.pazar" label="Pazar özetinin dayandığı kayıt" />}
        </h2>
        {c.pazar?.metin ? (
          <>
            <p className="mb-1 text-[11px] text-canvas-muted">{c.pazar.donemAd ?? c.pazar.donem} · onaylayan {c.pazar.onaylayan ?? '—'}</p>
            <div className="whitespace-pre-wrap break-words text-[12.5px] leading-relaxed">{c.pazar.metin}</div>
          </>
        ) : <Empty>Onaylı pazar özeti yok.</Empty>}
      </Panel>
    </>
  );
}
