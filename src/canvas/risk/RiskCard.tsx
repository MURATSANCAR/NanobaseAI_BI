import { useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, ClipboardCheck, Download, Loader2, Pencil, Plus, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText } from '../admin/ui';
import { Panel } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { fmtDay, fmtLeft, fmtTime, fmtValue, riskApi, type Action, type RiskDetail, type RiskMeta } from './api';
import { AskSheet, Empty, Fact, FilePick, LevelPill, RiskFrame, ScalePick, SelectInput, TextInput, ValuePill } from './parts';
import { RiskSheet } from './RiskScreen';

/** Risk kartı: tanım, neden/sonuç, bağlı göstergelerin son değerleri, aksiyonlar, gözden geçirme geçmişi. Telefonda
 *  sahibinin en sık iki işi üstte: «Gözden geçir» ve aksiyonu «Tamamlandı» yapmak. */
export default function RiskCard() {
  const { id = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['risk', 'meta'], queryFn: riskApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['risk', 'detail', id], queryFn: () => riskApi.risk(id), enabled: ENGINE_ENABLED && !!id });
  const ind = useQuery({ queryKey: ['risk', 'indicators'], queryFn: riskApi.indicators, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const [editing, setEditing] = useState(false);
  const [accepting, setAccepting] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const reviewing = params.get('gozden') === '1';
  const setReviewing = (on: boolean) => {
    const p = new URLSearchParams(params);
    if (on) p.set('gozden', '1');
    else p.delete('gozden');
    setParams(p, { replace: true });
  };
  const reject = useMutation({
    mutationFn: (note: string) => riskApi.reject(id, note),
    onSuccess: () => { toast.success('Öneri reddedildi'); setRejecting(false); qc.invalidateQueries({ queryKey: ['risk'] }); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  const r = q.data;
  const m = meta.data;
  return (
    <RiskFrame back title={r?.baslik ?? 'Risk'} lead={r ? `${r.kategoriAdi}${r.altKategori ? ` · ${r.altKategori}` : ''} · ${r.durumAdi} · ${r.kaynakAdi}` : 'Risk kartı'}
      aside={r && m && r.yazabilir ? (
        <div className="flex flex-wrap justify-start gap-2 lg:justify-end">
          {r.durum === 'oneri' ? (
            <>
              <button type="button" className={btnPrimary} onClick={() => setAccepting(true)}><Check aria-hidden className="h-4 w-4" />Kabul et ve puanla</button>
              <button type="button" className={btnGhost} onClick={() => setRejecting(true)}><X aria-hidden className="h-4 w-4" />Reddet</button>
            </>
          ) : r.durum !== 'kapandi' && r.durum !== 'reddedildi' ? (
            <button type="button" className={btnPrimary} onClick={() => setReviewing(true)}><ClipboardCheck aria-hidden className="h-4 w-4" />Gözden geçir</button>
          ) : null}
          <button type="button" className={btnGhost} onClick={() => setEditing(true)}><Pencil aria-hidden className="h-4 w-4" />Düzenle</button>
        </div>
      ) : undefined}>
      {(q.isLoading || meta.isLoading) && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Risk okunamadı.')}</Note>}
      {r && m && (
        <>
          {r.durum === 'oneri' && <Note tone="info">Zeki AI önerisi: metni kontrol edin, olasılık ve etkiyi siz verin. Kabul etmeden risk kaydına girmez.</Note>}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Fact label="Puan" value={<LevelPill level={r.seviye} score={r.puan} meta={m} />} help={r.olasilik && r.etki ? `olasılık ${r.olasilik} × etki ${r.etki}` : 'puanlanmadı'} />
            <Fact label="Sahip" value={r.sahip ?? '—'} help={r.egilim ? `eğilim: ${m.egilimler[r.egilim]}` : undefined} />
            <Fact label="Son gözden geçirme" value={r.sonGozdenGecirme ? fmtTime(r.sonGozdenGecirme) : 'hiç'} />
            <Fact label="Sonraki" value={fmtDay(r.sonrakiGozdenGecirme)} help={fmtLeft(r.gozdenGecirmeKalan)} />
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-4">
            <Panel>
              <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Tanım</h2>
              <div className="space-y-2 text-[12.5px] leading-relaxed">
                <p className="whitespace-pre-wrap break-words">{r.tanim ?? <span className="text-canvas-muted">Tanım yazılmamış.</span>}</p>
                {r.neden && <p className="whitespace-pre-wrap break-words"><b>Neden:</b> {r.neden}</p>}
                {r.sonuc && <p className="whitespace-pre-wrap break-words"><b>Sonuç:</b> {r.sonuc}</p>}
              </div>
            </Panel>
            <Panel>
              <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Bağlı göstergeler</h2>
              {r.gostergeler.length === 0 ? <Empty>Bağlı gösterge yok. Riskin büyüyüp büyümediğini görmek için «Düzenle»den gösterge bağlayın.</Empty> : (
                <ul className="flex flex-col gap-1.5">
                  {r.gostergeler.map((k) => {
                    const g = ind.data?.items.find((x) => x.kod === k);
                    return (
                      <li key={k} className="flex items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2">
                        <span className="min-w-0">
                          <span className="block break-words text-[12.5px] font-bold">{g?.ad ?? k}</span>
                          <span className="block text-[11px] text-canvas-muted">{g?.son ? `ölçüm ${fmtTime(g.son.olcum)}` : 'ölçülmedi'}</span>
                        </span>
                        <span className="flex shrink-0 items-center gap-2">
                          <span className="font-mono text-[13px] font-bold tabular-nums">{fmtValue(g?.son?.deger ?? null, g?.birim ?? '')}</span>
                          <ValuePill state={g?.son?.durum} meta={m} />
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Panel>
          </div>
          <Actions r={r} meta={m} />
          <Panel>
            <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Gözden geçirme geçmişi</h2>
            {r.gozdenGecirmeler.length === 0 ? <Empty>Henüz gözden geçirilmedi.</Empty> : (
              <ul className="flex flex-col gap-1.5">
                {r.gozdenGecirmeler.map((v) => (
                  <li key={v.id} className="rounded-xl bg-white/80 px-3 py-2 text-[12px] leading-snug">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <b>{fmtTime(v.tarih)} · {v.gozdenGeciren}</b>
                      <span className="font-mono tabular-nums">{v.eskiPuan ?? '—'} → {v.yeniPuan ?? '—'}{v.egilim ? ` · ${m.egilimler[v.egilim]}` : ''}</span>
                    </div>
                    {v.not && <p className="mt-0.5 whitespace-pre-wrap break-words">{v.not}</p>}
                    {v.tetik.length > 0 && (
                      <p className="mt-0.5 text-canvas-muted">O anki göstergeler: {v.tetik.map((t) => `${t.ad} ${t.deger ?? '—'}${t.durum ? ` (${m.degerDurumlari[t.durum as keyof typeof m.degerDurumlari] ?? t.durum})` : ''}`).join(' · ')}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          {editing && (
            <RiskSheet open id={r.id} meta={m} onClose={() => setEditing(false)} initial={{
              baslik: r.baslik, tanim: r.tanim ?? '', neden: r.neden ?? '', sonuc: r.sonuc ?? '', kategori: r.kategori, altKategori: r.altKategori ?? '',
              sahip: r.sahip ?? '', sahipEposta: r.sahipEposta ?? '', gostergeler: r.gostergeler, durum: r.durum,
            }} />
          )}
          {(reviewing || accepting) && (
            <ReviewSheet key={accepting ? 'accept' : 'review'} r={r} meta={m} accept={accepting}
              onClose={() => { setAccepting(false); setReviewing(false); }} />
          )}
          <AskSheet open={rejecting} title="Öneriyi reddet" message="Öneri risk kaydına girmez; kayıt «reddedildi» olarak kalır." confirm="Reddet" danger
            input="Gerekçe" busy={reject.isPending} onClose={() => setRejecting(false)} onConfirm={(t) => reject.mutate(t)} />
        </>
      )}
    </RiskFrame>
  );
}

function ReviewSheet({ r, meta, accept, onClose }: { r: RiskDetail; meta: RiskMeta; accept: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [o, setO] = useState<number | null>(r.olasilik);
  const [e, setE] = useState<number | null>(r.etki);
  const [egilim, setEgilim] = useState(r.egilim ?? '');
  const [note, setNote] = useState('');
  const save = useMutation({
    mutationFn: () => (accept
      ? riskApi.accept(r.id, { olasilik: o, etki: e })
      : riskApi.review(r.id, { olasilik: o as number, etki: e as number, egilim: egilim || undefined, not: note })),
    onSuccess: () => {
      toast.success(accept ? 'Öneri kabul edildi' : 'Gözden geçirme kaydedildi');
      qc.invalidateQueries({ queryKey: ['risk'] });
      onClose();
    },
    onError: (err) => toast.error(errText(err, 'Kaydedilemedi.')),
  });
  const score = o && e ? o * e : null;
  return (
    <Sheet open modal onClose={onClose} title={accept ? 'Öneriyi kabul et' : 'Gözden geçir'}
      subtitle={accept ? 'Puanı siz verirsiniz; Zeki AI puanlamaz.' : 'Puan aynı kalabilir; not ve eğilim iz bırakır, sonraki gözden geçirme tarihi ileri alınır.'}>
      <form className="flex flex-col gap-3" onSubmit={(ev) => { ev.preventDefault(); save.mutate(); }}>
        <ScalePick label="Olasılık" value={o} onChange={setO} hints={['çok düşük', 'çok yüksek']} />
        <ScalePick label="Etki" value={e} onChange={setE} hints={['önemsiz', 'çok ağır']} />
        <div className="text-[12.5px]">Puan: <b className="font-mono tabular-nums">{score ?? '—'}</b>{r.puan && score !== r.puan ? <span className="text-canvas-muted"> (önce {r.puan})</span> : null}</div>
        {!accept && (
          <>
            <SelectInput id="rv-egilim" label="Eğilim" value={egilim} onChange={setEgilim} options={meta.egilimler} empty="—" />
            <TextInput id="rv-not" label="Not" area value={note} onChange={setNote} placeholder="Ne değişti, ne yapıyoruz?" />
          </>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="submit" className={btnPrimary} disabled={save.isPending || !o || !e}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </div>
      </form>
    </Sheet>
  );
}

function Actions({ r, meta }: { r: RiskDetail; meta: RiskMeta }) {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState({ eylem: '', sahip: '', sahipEposta: '', termin: '' });
  const add = useMutation({
    mutationFn: () => riskApi.addAction(r.id, f),
    onSuccess: () => {
      toast.success('Aksiyon eklendi');
      setF({ eylem: '', sahip: '', sahipEposta: '', termin: '' });
      setAdding(false);
      qc.invalidateQueries({ queryKey: ['risk'] });
    },
    onError: (e) => toast.error(errText(e, 'Eklenemedi.')),
  });
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-extrabold tracking-tight">Aksiyonlar</h2>
        {r.yazabilir && !adding && <button type="button" className={btnGhost} onClick={() => setAdding(true)}><Plus aria-hidden className="h-4 w-4" />Aksiyon</button>}
      </div>
      {adding && (
        <form className="mb-3 flex flex-col gap-2 rounded-xl bg-white/80 p-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <TextInput id="ac-eylem" label="Aksiyon" value={f.eylem} onChange={(v) => setF({ ...f, eylem: v })} />
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <TextInput id="ac-sahip" label="Sahip" value={f.sahip} onChange={(v) => setF({ ...f, sahip: v })} />
            <TextInput id="ac-ep" label="E-posta" type="email" value={f.sahipEposta} onChange={(v) => setF({ ...f, sahipEposta: v })} />
            <TextInput id="ac-termin" label="Termin" type="date" value={f.termin} onChange={(v) => setF({ ...f, termin: v })} />
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" className={btnGhost} onClick={() => setAdding(false)}>Vazgeç</button>
            <button type="submit" className={btnPrimary} disabled={add.isPending || !f.eylem.trim()}>Ekle</button>
          </div>
        </form>
      )}
      {r.aksiyonlar.length === 0 ? <Empty>Aksiyon yok.</Empty> : (
        <ul className="flex flex-col gap-1.5">
          {r.aksiyonlar.map((a) => <ActionRow key={a.id} a={a} r={r} meta={meta} />)}
        </ul>
      )}
    </Panel>
  );
}

function ActionRow({ a, r, meta }: { a: Action; r: RiskDetail; meta: RiskMeta }) {
  const qc = useQueryClient();
  const mine = [a.sahip, r.sahip].some((s) => s && s.toLowerCase() === meta.me.username.toLowerCase());
  const can = r.yazabilir || mine;
  const set = useMutation({
    mutationFn: (durum: string) => riskApi.updateAction(a.id, { durum }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['risk'] }),
    onError: (e) => toast.error(errText(e, 'Güncellenemedi.')),
  });
  const up = useMutation({
    mutationFn: (file: File) => riskApi.actionEvidence(a.id, file),
    onSuccess: () => { toast.success('Kanıt yüklendi'); qc.invalidateQueries({ queryKey: ['risk'] }); },
    onError: (e) => toast.error(errText(e, 'Yüklenemedi.')),
  });
  const done = a.durum === 'tamamlandi';
  return (
    <li className="flex flex-col gap-2 rounded-xl bg-white/80 px-3 py-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <span className="min-w-0">
          <span className={`block break-words text-[13px] font-bold ${done ? 'text-canvas-muted line-through' : ''}`}>{a.eylem}</span>
          <span className="block text-[11px] text-canvas-muted">
            {a.sahip ?? 'sahip yok'}{a.termin ? ` · termin ${fmtDay(a.termin)}` : ''}{done && a.tamamlayan ? ` · ${a.tamamlayan} tamamladı` : ''}
          </span>
        </span>
        <span className="flex flex-wrap gap-1.5">
          <Pill tone={done ? 'ok' : a.gecikti ? 'err' : a.durum === 'iptal' ? 'muted' : 'violet'}>{a.durumAdi}</Pill>
          {!done && a.termin && a.durum !== 'iptal' && <Pill tone={a.gecikti ? 'err' : 'muted'}>{fmtLeft(a.kalanGun)}</Pill>}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {can && !done && a.durum !== 'iptal' && (
          <button type="button" className={btnPrimary} disabled={set.isPending} onClick={() => set.mutate('tamamlandi')}>
            <Check aria-hidden className="h-4 w-4" />Tamamlandı
          </button>
        )}
        {can && a.durum === 'acik' && <button type="button" className={btnGhost} disabled={set.isPending} onClick={() => set.mutate('devam')}>Sürüyor</button>}
        {can && done && <button type="button" className={btnGhost} disabled={set.isPending} onClick={() => set.mutate('acik')}>Yeniden aç</button>}
        {a.kanitVar && <a className={btnGhost} href={riskApi.actionEvidenceUrl(a.id)}><Download aria-hidden className="h-4 w-4" />{a.kanitAd}</a>}
        {can && <FilePick label={up.isPending ? 'Yükleniyor…' : a.kanitVar ? 'Kanıtı değiştir' : 'Kanıt ekle'} accept=".pdf,.docx,.doc,.xlsx,.xls,.csv,.txt,.jpg,.jpeg,.png"
          disabled={up.isPending} onPick={(file) => up.mutate(file)} />}
      </div>
    </li>
  );
}
