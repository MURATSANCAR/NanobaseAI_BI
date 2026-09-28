import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { dijitalApi, type Meta, type Platform } from './api';
import SqlInfo from '../components/SqlInfo';

/** Platform tanımları: e-kitap / sesli / abonelik platformu, dağıtım biçimi, rapor para birimi ve raporun ay kapanışından
 *  kaç gün sonra beklendiği (finans hatırlatması). Portal platformlara bağlanmaz; yalnız kayıt. */

const EMPTY = { ad: '', tur: 'ekitap', dagitim: 'dogrudan', paraBirimi: 'TRY', raporGunu: '' };

export default function PlatformsTab({ meta }: { meta: Meta }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['dijital', 'platforms'], queryFn: dijitalApi.platforms, enabled: ENGINE_ENABLED });
  const [editing, setEditing] = useState<Platform | null>(null);
  const [f, setF] = useState(EMPTY);
  const can = meta.me.canWrite;
  const save = useMutation({
    mutationFn: () => {
      const b = { ad: f.ad.trim(), tur: f.tur, dagitim: f.dagitim, paraBirimi: f.paraBirimi.trim().toUpperCase(),
                  raporGunu: f.raporGunu.trim() === '' ? null : Number(f.raporGunu) };
      return editing ? dijitalApi.updatePlatform(editing.id, b) : dijitalApi.createPlatform(b);
    },
    onSuccess: () => {
      toast.success(editing ? 'Platform güncellendi.' : 'Platform eklendi.');
      setEditing(null);
      setF(EMPTY);
      qc.invalidateQueries({ queryKey: ['dijital'] });
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const toggle = useMutation({
    mutationFn: (p: Platform) => dijitalApi.updatePlatform(p.id, { aktif: !p.aktif }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dijital'] }),
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const set = (k: keyof typeof EMPTY) => (v: string) => setF((x) => ({ ...x, [k]: v }));
  return (
    <>
      <Panel>
        <h2 className="flex items-center gap-1 text-[15px] font-extrabold">
          Platformlar
          <SqlInfo k={q.data?.kaynaklar} alan="items[]" label="Platform tanımları (rapor günü)" />
        </h2>
        <p className="mt-0.5 max-w-[80ch] text-[12px] leading-snug text-canvas-muted">
          Kitapların durumunu işaretlediğiniz ve satış raporunu yüklediğiniz platformlar. Yükleme platformun kendi panelinden ya da
          dağıtıcıdan yapılır; portal hiçbir platforma bağlanmaz.
        </p>
        {q.error && <Note tone="err">{errText(q.error, 'Liste okunamadı.')}</Note>}
        <div className="mt-3 flex flex-col gap-2">
          {q.data && !q.data.items.length && <div className="py-6 text-center text-[12.5px] text-canvas-muted">Henüz platform tanımlanmadı.</div>}
          {q.data?.items.map((p) => (
            <div key={p.id} className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[13.5px] font-extrabold">{p.ad}</span>
                  <Pill tone={p.aktif ? 'ok' : 'muted'}>{p.aktif ? 'Etkin' : 'Kapalı'}</Pill>
                </div>
                <div className="text-[12px] text-canvas-muted">
                  {p.turAdi} · {p.dagitimAdi} · {p.paraBirimi}
                  {p.raporGunu !== null ? ` · rapor ay kapanışından ${p.raporGunu} gün sonra` : ' · rapor günü tanımsız (hatırlatma yok)'}
                </div>
              </div>
              {can && (
                <div className="flex gap-1.5">
                  <button type="button" className={btnGhost} onClick={() => {
                    setEditing(p);
                    setF({ ad: p.ad, tur: p.tur, dagitim: p.dagitim, paraBirimi: p.paraBirimi, raporGunu: p.raporGunu === null ? '' : String(p.raporGunu) });
                  }}>Düzenle</button>
                  <button type="button" className={btnGhost} disabled={toggle.isPending} onClick={() => toggle.mutate(p)}>{p.aktif ? 'Kapat' : 'Aç'}</button>
                </div>
              )}
            </div>
          ))}
        </div>
      </Panel>
      {can && (
        <Panel>
          <h2 className="text-[15px] font-extrabold">{editing ? `${editing.ad} — düzenle` : 'Platform ekle'}</h2>
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Ad</span>
              <input className={field} value={f.ad} onChange={(e) => set('ad')(e.target.value)} placeholder="Örn. Kindle, Google Play Kitaplar" />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Tür</span>
              <select className={field} value={f.tur} onChange={(e) => set('tur')(e.target.value)}>
                {Object.entries(meta.platformTurleri).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Dağıtım</span>
              <select className={field} value={f.dagitim} onChange={(e) => set('dagitim')(e.target.value)}>
                {Object.entries(meta.dagitim).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Rapor para birimi</span>
              <input className={field} value={f.paraBirimi} maxLength={3} onChange={(e) => set('paraBirimi')(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Rapor günü (ay kapanışından sonra)</span>
              <input className={field} inputMode="numeric" value={f.raporGunu} onChange={(e) => set('raporGunu')(e.target.value.replace(/\D/g, ''))} placeholder="boş: hatırlatma yok" />
            </label>
          </div>
          <div className="mt-3 flex flex-wrap justify-end gap-2">
            {editing && <button type="button" className={btnGhost} onClick={() => { setEditing(null); setF(EMPTY); }}>Vazgeç</button>}
            <button type="button" className={btnPrimary} disabled={!f.ad.trim() || f.paraBirimi.trim().length !== 3 || save.isPending} onClick={() => save.mutate()}>
              {!editing && <Plus aria-hidden className="h-4 w-4" />}
              {editing ? 'Kaydet' : 'Ekle'}
            </button>
          </div>
        </Panel>
      )}
    </>
  );
}
