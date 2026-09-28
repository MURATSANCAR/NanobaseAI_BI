import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, Loader2, Plus, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText } from '../admin/ui';
import { Panel } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { fmtDay, fmtLeft, fmtMoney, fmtNum, parseNum, riskApi, type Bcp, type Policy, type RiskMeta } from './api';
import { AskSheet, Empty, FilePick, ScalePick, SelectInput, TextInput } from './parts';

/** Sigorta poliçeleri (tür, teminat, bitiş; poliçe numarası yalnız maskeli) ve iş sürekliliği süreçleri (kabul edilebilir
 *  kesinti, tatbikat). Hepsini kullanıcı girer; bitişe 60 gün kala ve geciken tatbikat sorumluya hatırlatılır. */
export default function ContinuityTab({ meta }: { meta: RiskMeta }) {
  const pol = useQuery({ queryKey: ['risk', 'policies'], queryFn: riskApi.policies, enabled: ENGINE_ENABLED });
  const bcp = useQuery({ queryKey: ['risk', 'bcp'], queryFn: riskApi.bcp, enabled: ENGINE_ENABLED });
  const [policy, setPolicy] = useState<Policy | 'new' | null>(null);
  const [proc, setProc] = useState<Bcp | 'new' | null>(null);
  const can = meta.me.canPolicy;
  return (
    <>
      <Panel>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[15px] font-extrabold tracking-tight">Sigorta poliçeleri</h2>
          {can && <button type="button" className={btnPrimary} onClick={() => setPolicy('new')}><Plus aria-hidden className="h-4 w-4" />Poliçe ekle</button>}
        </div>
        {pol.isLoading ? <Loading /> : pol.error ? <Note tone="err">{errText(pol.error, 'Poliçeler okunamadı.')}</Note> :
          (pol.data?.items.length ?? 0) === 0 ? <Empty>Kayıtlı poliçe yok.</Empty> : (
            <ul className="flex flex-col gap-2">
              {pol.data!.items.map((p) => <PolicyRow key={p.id} p={p} can={can} onEdit={() => setPolicy(p)} />)}
            </ul>
          )}
      </Panel>
      <Panel>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[15px] font-extrabold tracking-tight">İş sürekliliği (kritik süreçler)</h2>
          {can && <button type="button" className={btnPrimary} onClick={() => setProc('new')}><Plus aria-hidden className="h-4 w-4" />Süreç ekle</button>}
        </div>
        {bcp.isLoading ? <Loading /> : bcp.error ? <Note tone="err">{errText(bcp.error, 'Süreçler okunamadı.')}</Note> :
          (bcp.data?.items.length ?? 0) === 0 ? <Empty>Kayıtlı süreç yok. Depo, matbaa, Logo/CRM erişimi, kargo gibi durduğunda satışı kesen süreçleri ekleyin.</Empty> : (
            <ul className="flex flex-col gap-2">
              {bcp.data!.items.map((b) => (
                <li key={b.id} className="flex flex-col gap-1 rounded-xl bg-white/80 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
                  <span className="min-w-0">
                    <span className="block break-words text-[13px] font-bold">{b.surec}</span>
                    <span className="block text-[11px] text-canvas-muted">
                      kritiklik {b.kritiklik ?? '—'} · kabul edilebilir kesinti {fmtNum(b.kabulKesintiSaat)} sa · veri kaybı {fmtNum(b.veriKaybiSaat)} sa
                      {b.sorumlu ? ` · ${b.sorumlu}` : ''}{b.belgeSurum ? ` · plan ${b.belgeSurum}` : ''}
                    </span>
                  </span>
                  <span className="flex flex-wrap items-center gap-1.5">
                    <Pill tone={b.durum === 'onayli' ? 'ok' : b.durum === 'guncellenecek' ? 'warn' : 'muted'}>{b.durumAdi}</Pill>
                    {b.sonrakiTatbikat && <Pill tone={b.tatbikatGecikti ? 'err' : 'muted'}>tatbikat {fmtLeft(b.tatbikatKalan)}</Pill>}
                    {can && <button type="button" className={btnGhost} onClick={() => setProc(b)}>Düzenle</button>}
                  </span>
                </li>
              ))}
            </ul>
          )}
      </Panel>
      {policy && <PolicySheet key={policy === 'new' ? 'new' : policy.id} p={policy === 'new' ? null : policy} onClose={() => setPolicy(null)} />}
      {proc && <BcpSheet key={proc === 'new' ? 'new' : proc.id} b={proc === 'new' ? null : proc} meta={meta} onClose={() => setProc(null)} />}
    </>
  );
}

function PolicyRow({ p, can, onEdit }: { p: Policy; can: boolean; onEdit: () => void }) {
  const qc = useQueryClient();
  const [del, setDel] = useState(false);
  const up = useMutation({
    mutationFn: (f: File) => riskApi.policyDocument(p.id, f),
    onSuccess: () => { toast.success('Belge yüklendi'); qc.invalidateQueries({ queryKey: ['risk', 'policies'] }); },
    onError: (e) => toast.error(errText(e, 'Yüklenemedi.')),
  });
  const remove = useMutation({
    mutationFn: () => riskApi.deletePolicy(p.id),
    onSuccess: () => { toast.success('Poliçe silindi'); setDel(false); qc.invalidateQueries({ queryKey: ['risk', 'policies'] }); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.')),
  });
  return (
    <li className="flex flex-col gap-2 rounded-xl bg-white/80 px-3 py-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <span className="min-w-0">
          <span className="block break-words text-[13px] font-bold">{p.tur}{p.sigortaci ? ` — ${p.sigortaci}` : ''}</span>
          <span className="block text-[11px] text-canvas-muted">
            {p.policeNo ?? 'numara yok'} · {fmtDay(p.bas)} – {fmtDay(p.bit)}{p.prim !== null ? ` · prim ${fmtMoney(p.prim)}` : ''}{p.sorumlu ? ` · ${p.sorumlu}` : ''}
          </span>
          {p.teminat.length > 0 && <span className="block text-[11px]">{p.teminat.map((t) => `${t.ad}: ${fmtMoney(t.tutar)}`).join(' · ')}</span>}
          {p.not && <span className="block text-[11px] text-amber-800">Boşluk: {p.not}</span>}
        </span>
        {p.bit && <Pill tone={p.bitti ? 'err' : p.yaklasti ? 'warn' : 'ok'}>{p.bitti ? 'süresi doldu' : fmtLeft(p.kalanGun)}</Pill>}
      </div>
      <div className="flex flex-wrap gap-2">
        {p.belgeVar && <a className={btnGhost} href={riskApi.policyDocumentUrl(p.id)}><Download aria-hidden className="h-4 w-4" />{p.belgeAd}</a>}
        <FilePick label={up.isPending ? 'Yükleniyor…' : p.belgeVar ? 'Belgeyi değiştir' : 'Poliçe belgesi yükle'} accept=".pdf,.docx,.doc,.jpg,.jpeg,.png"
          allowed={can} feature="risk.sigorta-bcp" disabled={up.isPending} onPick={(f) => up.mutate(f)} />
        {can && (
          <>
            <button type="button" className={btnGhost} onClick={onEdit}>Düzenle</button>
            <button type="button" className={btnGhost} aria-label="Sil" onClick={() => setDel(true)}><Trash2 aria-hidden className="h-4 w-4" /></button>
          </>
        )}
      </div>
      <AskSheet open={del} title="Poliçeyi sil" message={`«${p.tur}» kaydı ve belgesi silinir.`} confirm="Sil" danger busy={remove.isPending}
        onClose={() => setDel(false)} onConfirm={() => remove.mutate()} />
    </li>
  );
}

function PolicySheet({ p, onClose }: { p: Policy | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ tur: p?.tur ?? '', sigortaci: p?.sigortaci ?? '', policeNo: '', prim: p && p.prim !== null ? String(p.prim) : '',
    bas: p?.bas ?? '', bit: p?.bit ?? '', sorumlu: p?.sorumlu ?? '', sorumluEposta: p?.sorumluEposta ?? '', not: p?.not ?? '' });
  const [cover, setCover] = useState((p?.teminat ?? []).map((t) => ({ ad: t.ad, tutar: t.tutar === null ? '' : String(t.tutar) })));
  const set = (k: keyof typeof f, v: string) => setF((x) => ({ ...x, [k]: v }));
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { ...f, prim: parseNum(f.prim), teminat: cover.filter((c) => c.ad.trim()).map((c) => ({ ad: c.ad, tutar: parseNum(c.tutar) })) };
      if (!f.policeNo.trim()) delete body.policeNo;           // boş bırakılırsa kayıtlı maske korunur
      return riskApi.savePolicy(p?.id ?? null, body);
    },
    onSuccess: () => { toast.success('Poliçe kaydedildi'); qc.invalidateQueries({ queryKey: ['risk', 'policies'] }); onClose(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  return (
    <Sheet open modal onClose={onClose} title={p ? 'Poliçeyi düzenle' : 'Yeni poliçe'} subtitle="Poliçe numarasının yalnız son 4 hanesi saklanır.">
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextInput id="po-tur" label="Tür" value={f.tur} onChange={(v) => set('tur', v)} placeholder="Yangın, nakliyat, sorumluluk…" />
          <TextInput id="po-sig" label="Sigortacı" value={f.sigortaci} onChange={(v) => set('sigortaci', v)} />
          <TextInput id="po-no" label="Poliçe numarası" value={f.policeNo} onChange={(v) => set('policeNo', v)} help={p?.policeNo ? `Kayıtlı: ${p.policeNo}` : undefined} />
          <TextInput id="po-prim" label="Prim (₺)" value={f.prim} onChange={(v) => set('prim', v)} />
          <TextInput id="po-bas" label="Başlangıç" type="date" value={f.bas} onChange={(v) => set('bas', v)} />
          <TextInput id="po-bit" label="Bitiş" type="date" value={f.bit} onChange={(v) => set('bit', v)} />
          <TextInput id="po-sor" label="Sorumlu" value={f.sorumlu} onChange={(v) => set('sorumlu', v)} />
          <TextInput id="po-ep" label="Sorumlunun e-postası" type="email" value={f.sorumluEposta} onChange={(v) => set('sorumluEposta', v)} />
        </div>
        <fieldset className="flex flex-col gap-2">
          <legend className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Teminatlar</legend>
          {cover.map((c, i) => (
            <div key={i} className="grid grid-cols-[minmax(0,1fr)_minmax(0,140px)_auto] items-end gap-2">
              <TextInput id={`po-t${i}`} label="Teminat" value={c.ad} onChange={(v) => setCover(cover.map((x, j) => (j === i ? { ...x, ad: v } : x)))} />
              <TextInput id={`po-tt${i}`} label="Tutar (₺)" value={c.tutar} onChange={(v) => setCover(cover.map((x, j) => (j === i ? { ...x, tutar: v } : x)))} />
              <button type="button" className={btnGhost} aria-label="Teminatı kaldır" onClick={() => setCover(cover.filter((_, j) => j !== i))}><Trash2 aria-hidden className="h-4 w-4" /></button>
            </div>
          ))}
          <button type="button" className={`${btnGhost} self-start`} onClick={() => setCover([...cover, { ad: '', tutar: '' }])}><Plus aria-hidden className="h-4 w-4" />Teminat</button>
        </fieldset>
        <TextInput id="po-not" label="Boşluk notu" area value={f.not} onChange={(v) => set('not', v)} help="Teminat dışında kalan riskler (ör. stok değeri, iş durması)" />
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="submit" className={btnPrimary} disabled={save.isPending || !f.tur.trim()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </div>
      </form>
    </Sheet>
  );
}

function BcpSheet({ b, meta, onClose }: { b: Bcp | null; meta: RiskMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ surec: b?.surec ?? '', kabulKesintiSaat: b && b.kabulKesintiSaat !== null ? String(b.kabulKesintiSaat) : '',
    veriKaybiSaat: b && b.veriKaybiSaat !== null ? String(b.veriKaybiSaat) : '', sorumlu: b?.sorumlu ?? '',
    sorumluEposta: b?.sorumluEposta ?? '', sonTatbikat: b?.sonTatbikat ?? '', sonrakiTatbikat: b?.sonrakiTatbikat ?? '', belgeSurum: b?.belgeSurum ?? '',
    durum: b?.durum ?? 'taslak', not: b?.not ?? '' });
  const [kritik, setKritik] = useState<number | null>(b?.kritiklik ?? null);
  const [del, setDel] = useState(false);
  const set = (k: keyof typeof f, v: string) => setF((x) => ({ ...x, [k]: v }));
  const save = useMutation({
    mutationFn: () => riskApi.saveBcp(b?.id ?? null, { ...f, kritiklik: kritik, kabulKesintiSaat: parseNum(f.kabulKesintiSaat), veriKaybiSaat: parseNum(f.veriKaybiSaat),
      sonTatbikat: f.sonTatbikat || null, sonrakiTatbikat: f.sonrakiTatbikat || null }),
    onSuccess: () => { toast.success('Süreç kaydedildi'); qc.invalidateQueries({ queryKey: ['risk', 'bcp'] }); onClose(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  const remove = useMutation({
    mutationFn: () => riskApi.deleteBcp(b!.id),
    onSuccess: () => { toast.success('Süreç silindi'); qc.invalidateQueries({ queryKey: ['risk', 'bcp'] }); onClose(); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.')),
  });
  return (
    <Sheet open modal onClose={onClose} title={b ? 'Süreci düzenle' : 'Yeni kritik süreç'}>
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <TextInput id="bc-surec" label="Süreç" value={f.surec} onChange={(v) => set('surec', v)} placeholder="ör. Depodan sevkiyat" />
        <ScalePick label="Kritiklik" value={kritik} onChange={setKritik} hints={['düşük', 'çok yüksek']} />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextInput id="bc-rto" label="Kabul edilebilir kesinti (saat)" value={f.kabulKesintiSaat} onChange={(v) => set('kabulKesintiSaat', v)} />
          <TextInput id="bc-rpo" label="Kabul edilebilir veri kaybı (saat)" value={f.veriKaybiSaat} onChange={(v) => set('veriKaybiSaat', v)} />
          <TextInput id="bc-sor" label="Sorumlu" value={f.sorumlu} onChange={(v) => set('sorumlu', v)} />
          <TextInput id="bc-ep" label="Sorumlunun e-postası" type="email" value={f.sorumluEposta} onChange={(v) => set('sorumluEposta', v)} />
          <TextInput id="bc-son" label="Son tatbikat" type="date" value={f.sonTatbikat} onChange={(v) => set('sonTatbikat', v)} />
          <TextInput id="bc-sonraki" label="Sonraki tatbikat" type="date" value={f.sonrakiTatbikat} onChange={(v) => set('sonrakiTatbikat', v)} />
          <TextInput id="bc-surum" label="Plan belgesi sürümü" value={f.belgeSurum} onChange={(v) => set('belgeSurum', v)} />
          <SelectInput id="bc-durum" label="Durum" value={f.durum} onChange={(v) => set('durum', v)} options={meta.bcpDurumlari} />
        </div>
        <TextInput id="bc-not" label="Not" area value={f.not} onChange={(v) => set('not', v)} />
        <div className="flex flex-wrap justify-between gap-2">
          {b ? <button type="button" className={btnGhost} onClick={() => setDel(true)}><Trash2 aria-hidden className="h-4 w-4" />Sil</button> : <span />}
          <span className="flex gap-2">
            <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
            <button type="submit" className={btnPrimary} disabled={save.isPending || !f.surec.trim()}>
              {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
              Kaydet
            </button>
          </span>
        </div>
      </form>
      <AskSheet open={del} title="Süreci sil" message={`«${b?.surec ?? ''}» kaydı silinir.`} confirm="Sil" danger busy={remove.isPending}
        onClose={() => setDel(false)} onConfirm={() => remove.mutate()} />
    </Sheet>
  );
}
