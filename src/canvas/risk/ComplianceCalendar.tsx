import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ChevronLeft, ChevronRight, Download, Loader2, Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText } from '../admin/ui';
import { Panel } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { fmtDay, fmtLeft, monthLabel, monthShift, riskApi, type CompEvent, type CompItem, type RiskMeta } from './api';
import { AskSheet, Empty, FilePick, SelectInput, TextInput } from './parts';

/** Uyum: ayın yükümlülükleri (açılışta bu ay; geciken eski dönemler de görünür), kanıt yükleme ve dönemi kapatma;
 *  yükümlülük listesi. Takvimi insan kurar (müşteride dış kaynak taraması kapalı); sistem dönemleri sıklıktan açar. */
export default function ComplianceCalendar({ meta }: { meta: RiskMeta }) {
  const now = new Date();
  const [ay, setAy] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`);
  const [editing, setEditing] = useState<CompItem | 'new' | null>(null);
  const cal = useQuery({ queryKey: ['risk', 'calendar', ay], queryFn: () => riskApi.calendar(ay), enabled: ENGINE_ENABLED });
  const items = useQuery({ queryKey: ['risk', 'comp-items'], queryFn: riskApi.compItems, enabled: ENGINE_ENABLED });
  const kvkk = useQuery({ queryKey: ['risk', 'kvkk'], queryFn: riskApi.kvkk, enabled: ENGINE_ENABLED, staleTime: 300_000 });
  const canEdit = (alan: string) => meta.me.canCompliance && (alan !== 'kvkk' || meta.me.canKvkk);
  return (
    <>
      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-1">
            <button type="button" className={btnGhost} aria-label="Önceki ay" onClick={() => setAy(monthShift(ay, -1))}><ChevronLeft aria-hidden className="h-4 w-4" /></button>
            <h2 className="min-w-[140px] text-center text-[15px] font-extrabold capitalize tracking-tight">{monthLabel(ay)}</h2>
            <button type="button" className={btnGhost} aria-label="Sonraki ay" onClick={() => setAy(monthShift(ay, 1))}><ChevronRight aria-hidden className="h-4 w-4" /></button>
          </div>
          {meta.me.canCompliance && (
            <button type="button" className={btnPrimary} onClick={() => setEditing('new')}><Plus aria-hidden className="h-4 w-4" />Yükümlülük ekle</button>
          )}
        </div>
        <div className="mt-3">
          {cal.isLoading ? <Loading /> : cal.error ? <Note tone="err">{errText(cal.error, 'Takvim okunamadı.')}</Note> :
            (cal.data?.items.length ?? 0) === 0 ? <Empty>Bu ay son günü gelen ya da geciken yükümlülük yok.</Empty> : (
              <ul className="flex flex-col gap-2">
                {cal.data!.items.map((e) => <EventRow key={e.id} e={e} canEdit={canEdit(e.alan ?? '')} />)}
              </ul>
            )}
        </div>
      </Panel>
      <Panel>
        <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Yükümlülükler</h2>
        {items.isLoading ? <Loading /> : (items.data?.items.length ?? 0) === 0 ? (
          <Empty>Henüz yükümlülük yok. Telif, KVKK, vergi, ticaret ve iş sağlığı maddelerini son günü ve sıklığıyla ekleyin.</Empty>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {items.data!.items.map((it) => (
              <li key={it.id} className="flex flex-col gap-1 rounded-xl bg-white/80 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
                <span className="min-w-0">
                  <span className="block break-words text-[13px] font-bold">{it.madde}{!it.aktif && <span className="ml-1 text-canvas-muted">(pasif)</span>}</span>
                  <span className="block text-[11px] text-canvas-muted">
                    {it.alanAdi} · {it.siklikAdi}{it.dayanak ? ` · ${it.dayanak}` : ''}{it.sorumlu ? ` · ${it.sorumlu}` : ''}
                  </span>
                </span>
                <span className="flex flex-wrap items-center gap-2">
                  {it.geciken > 0 && <Pill tone="err">{it.geciken} geciken</Pill>}
                  {it.siradaki && <Pill tone="muted">sıradaki {fmtDay(it.siradaki.sonGun)}</Pill>}
                  <Pill tone="ok">{it.kapanan} kapandı</Pill>
                  {canEdit(it.alan) && <button type="button" className={btnGhost} onClick={() => setEditing(it)}>Düzenle</button>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <Panel>
        <h2 className="mb-1 text-[15px] font-extrabold tracking-tight">KVKK işleme envanteri</h2>
        <p className="text-[12px] leading-snug text-canvas-muted">
          {kvkk.data?.available ? 'Veri güvenliği modülündeki envanterin özeti.' : kvkk.data?.message ?? 'Kişisel veri işleme envanteri Veri güvenliği modülünde tutulur.'}
          {' '}Buradaki KVKK maddeleri yükümlülük takvimidir; kişisel verinin kendisi tutulmaz.
        </p>
      </Panel>
      {editing && <ItemSheet key={editing === 'new' ? 'new' : editing.id} item={editing === 'new' ? null : editing} meta={meta} onClose={() => setEditing(null)} />}
    </>
  );
}

function EventRow({ e, canEdit }: { e: CompEvent; canEdit: boolean }) {
  const qc = useQueryClient();
  const [closing, setClosing] = useState(false);
  const up = useMutation({
    mutationFn: (file: File) => riskApi.eventEvidence(e.id, file),
    onSuccess: () => { toast.success('Kanıt yüklendi'); qc.invalidateQueries({ queryKey: ['risk'] }); },
    onError: (err) => toast.error(errText(err, 'Yüklenemedi.')),
  });
  const close = useMutation({
    mutationFn: (note: string) => riskApi.closeEvent(e.id, note),
    onSuccess: () => { toast.success('Dönem kapandı'); setClosing(false); qc.invalidateQueries({ queryKey: ['risk'] }); },
    onError: (err) => toast.error(errText(err, 'Kapatılamadı.')),
  });
  const tone = e.durum === 'kapandi' ? 'ok' : e.gecikti ? 'err' : e.durum === 'kanit' ? 'violet' : (e.kalanGun ?? 99) <= 14 ? 'warn' : 'muted';
  return (
    <li className="flex flex-col gap-2 rounded-xl bg-white/80 px-3 py-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <span className="min-w-0">
          <span className="block break-words text-[13px] font-bold">{e.madde}</span>
          <span className="block text-[11px] text-canvas-muted">{e.alanAdi} · dönem {e.donem} · son gün {fmtDay(e.sonGun)}{e.sorumlu ? ` · ${e.sorumlu}` : ''}</span>
        </span>
        <span className="flex flex-wrap gap-1.5">
          <Pill tone={tone}>{e.durumAdi}</Pill>
          {e.durum !== 'kapandi' && <Pill tone={e.gecikti ? 'err' : 'muted'}>{fmtLeft(e.kalanGun)}</Pill>}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {e.kanitVar && (e.alan !== 'kvkk' || canEdit) && (
          <a className={btnGhost} href={riskApi.eventEvidenceUrl(e.id)}><Download aria-hidden className="h-4 w-4" />{e.kanitAd}</a>
        )}
        {canEdit && e.durum !== 'kapandi' && (
          <>
            <FilePick label={up.isPending ? 'Yükleniyor…' : e.kanitVar ? 'Kanıtı değiştir' : 'Kanıt yükle'} accept=".pdf,.docx,.doc,.xlsx,.xls,.csv,.txt,.jpg,.jpeg,.png"
              disabled={up.isPending} onPick={(f) => up.mutate(f)} />
            <button type="button" className={btnGhost} onClick={() => setClosing(true)}>Kapat</button>
          </>
        )}
        {e.durum === 'kapandi' && <span className="text-[11px] text-canvas-muted">{e.kapatan} kapattı{e.not ? ` — ${e.not}` : ''}</span>}
      </div>
      <AskSheet open={closing} title="Dönemi kapat" busy={close.isPending}
        message={e.kanitVar ? 'Kanıt yüklü; dönem kapanır.' : 'Kanıt yüklenmedi: kapanış için açıklama yazın (ör. «beyanname e-imzayla verildi, tahakkuk fişi muhasebede»).'}
        confirm="Kapat" input="Açıklama" required={!e.kanitVar} onClose={() => setClosing(false)} onConfirm={(t) => close.mutate(t)} />
    </li>
  );
}

function ItemSheet({ item, meta, onClose }: { item: CompItem | null; meta: RiskMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const areas = meta.me.canKvkk ? meta.alanlar : Object.fromEntries(Object.entries(meta.alanlar).filter(([k]) => k !== 'kvkk'));
  const [f, setF] = useState({
    alan: item?.alan ?? 'vergi', madde: item?.madde ?? '', dayanak: item?.dayanak ?? '', siklik: item?.siklik ?? 'aylik',
    ilkSonGun: item?.ilkSonGun ?? '', sorumlu: item?.sorumlu ?? '', sorumluEposta: item?.sorumluEposta ?? '', not: item?.not ?? '',
    aktif: item?.aktif ?? true,
  });
  const set = (k: keyof typeof f, v: string | boolean) => setF((p) => ({ ...p, [k]: v }));
  const save = useMutation({
    mutationFn: () => riskApi.saveItem(item?.id ?? null, f),
    onSuccess: () => { toast.success('Yükümlülük kaydedildi'); qc.invalidateQueries({ queryKey: ['risk'] }); onClose(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  return (
    <Sheet open modal onClose={onClose} title={item ? 'Yükümlülüğü düzenle' : 'Yeni uyum yükümlülüğü'}
      subtitle="Sistem dönemleri sıklıktan açar ve son güne 14 ve 3 gün kala sorumluya hatırlatır.">
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <SelectInput id="ci-alan" label="Alan" value={f.alan} onChange={(v) => set('alan', v)} options={areas} />
        <TextInput id="ci-madde" label="Yükümlülük" value={f.madde} onChange={(v) => set('madde', v)} placeholder="ör. Muhtasar ve prim hizmet beyannamesi" />
        <TextInput id="ci-dayanak" label="Dayanak" value={f.dayanak} onChange={(v) => set('dayanak', v)} placeholder="Kanun, yönetmelik, sözleşme maddesi" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <SelectInput id="ci-siklik" label="Sıklık" value={f.siklik} onChange={(v) => set('siklik', v)} options={meta.uyumSikliklari} />
          <TextInput id="ci-ilk" label="İlk son gün" type="date" value={f.ilkSonGun} onChange={(v) => set('ilkSonGun', v)} />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextInput id="ci-sorumlu" label="Sorumlu" value={f.sorumlu} onChange={(v) => set('sorumlu', v)} />
          <TextInput id="ci-eposta" label="Sorumlunun e-postası" type="email" value={f.sorumluEposta} onChange={(v) => set('sorumluEposta', v)} />
        </div>
        <TextInput id="ci-not" label="Not" area value={f.not} onChange={(v) => set('not', v)} />
        {item && (
          <label className="flex min-h-11 items-center gap-2 text-[12.5px] font-bold">
            <input type="checkbox" className="h-4 w-4" checked={f.aktif} onChange={(e) => set('aktif', e.target.checked)} />
            Etkin (pasif yükümlülüğe yeni dönem açılmaz)
          </label>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="submit" className={btnPrimary} disabled={save.isPending || !f.madde.trim() || !f.ilkSonGun}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </div>
      </form>
    </Sheet>
  );
}
