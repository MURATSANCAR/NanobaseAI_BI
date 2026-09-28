import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Play, Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label } from '../admin/ui';
import { Panel } from '../editorial/kit';
import {
  RUN_TONE, commerceApi, fmtDay, fmtInt, fmtRatio, paramText,
  type Channel, type Preview, type Run, type Trigger, type TriggerKind,
} from './api';
import { ROOT, useMeta } from './parts';

/** Tetikler: kural (yeni kitap, geri kazanım, ikinci sipariş), önizleme (yalnız sayı), liste (kontrol grubu ayrılır),
 * onay (yazan onaylayamaz), izin denetimli dışa aktarım ve kampanya açma. */
export default function Triggers() {
  const meta = useMeta();
  const me = meta.data?.me;
  const qc = useQueryClient();
  const triggers = useQuery({ queryKey: ['commerce', 'triggers'], queryFn: commerceApi.triggers, enabled: ENGINE_ENABLED });
  const runs = useQuery({ queryKey: ['commerce', 'runs'], queryFn: () => commerceApi.runs(), enabled: ENGINE_ENABLED });
  const [creating, setCreating] = useState(false);
  const [previews, setPreviews] = useState<Record<string, Preview>>({});

  const refresh = () => qc.invalidateQueries({ queryKey: ['commerce'] });
  const preview = useMutation({
    mutationFn: (id: string) => commerceApi.preview(id),
    onSuccess: (p, id) => setPreviews((x) => ({ ...x, [id]: p })),
    onError: (e) => toast.error(errText(e, 'Önizleme yapılamadı.') ?? ''),
  });
  const run = useMutation({
    mutationFn: (id: string) => commerceApi.run(id),
    onSuccess: (r) => { toast.success(`Liste hazır: ${fmtInt(r.target)} hedef, ${fmtInt(r.control)} kontrol. Onay bekliyor.`); refresh(); },
    onError: (e) => toast.error(errText(e, 'Liste çalıştırılamadı.') ?? ''),
  });
  const archive = useMutation({
    mutationFn: (id: string) => commerceApi.archiveTrigger(id),
    onSuccess: refresh,
    onError: (e) => toast.error(errText(e, 'Arşive kaldırılamadı.') ?? ''),
  });

  if (triggers.isLoading) return <Loading />;
  if (triggers.error) return <Note tone="err">{errText(triggers.error, 'Tetikler açılamadı.')}</Note>;
  const excl = meta.data?.excludeLabels ?? {};

  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      {meta.data && !meta.data.exportEnabled && (
        <Note tone="info">
          Liste dışa aktarımı okur veri tabanı ayarında kapalı (hukuk teyidi bekleniyor). Tetik çalışır, liste onaylanır; dosya ayar açılınca alınır.
        </Note>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-extrabold">Tetikler</h2>
        {me?.canTrigger && !creating && (
          <button type="button" className={btnPrimary} onClick={() => setCreating(true)}><Plus aria-hidden className="h-4 w-4" />Yeni tetik</button>
        )}
      </div>
      {creating && <TriggerForm onDone={() => { setCreating(false); refresh(); }} />}

      {(triggers.data?.items ?? []).length === 0 && !creating && (
        <Note tone="info">Henüz tetik yok. Yeni kitap, geri kazanım ya da ikinci sipariş tetiği kurulabilir; terk sepeti için site sepet verisi okunmuyor.</Note>
      )}
      <div className="grid gap-3 lg:grid-cols-2 lg:gap-4">
        {(triggers.data?.items ?? []).map((t) => (
          <TriggerCard key={t.id} t={t} p={previews[t.id]} excl={excl} canTrigger={!!me?.canTrigger}
            busy={preview.isPending && preview.variables === t.id} running={run.isPending && run.variables === t.id}
            onPreview={() => preview.mutate(t.id)} onRun={() => run.mutate(t.id)} onArchive={() => archive.mutate(t.id)} />
        ))}
      </div>

      <h2 className="mt-2 text-[15px] font-extrabold">Listeler</h2>
      {runs.error && <Note tone="err">{errText(runs.error, 'Listeler açılamadı.')}</Note>}
      {(runs.data?.items ?? []).length === 0 ? (
        <p className="text-[12.5px] text-canvas-muted">Henüz çalıştırılmış liste yok.</p>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2 lg:gap-4">
          {(runs.data?.items ?? []).map((r) => <RunCard key={r.id} r={r} excl={excl} onChange={refresh} />)}
        </div>
      )}
    </div>
  );
}

function TriggerCard({ t, p, excl, canTrigger, busy, running, onPreview, onRun, onArchive }: {
  t: Trigger; p?: Preview; excl: Record<string, string>; canTrigger: boolean; busy: boolean; running: boolean;
  onPreview: () => void; onRun: () => void; onArchive: () => void;
}) {
  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">{t.kindLabel} · {t.channelLabel}</div>
          <h3 className="text-[14px] font-extrabold">{t.name}</h3>
          <p className="text-[11.5px] text-canvas-muted">{paramText(t.kind, t.params)} · kontrol payı {fmtRatio(t.controlShare, 0)} · {t.owner}</p>
        </div>
        {t.lastRun && <Pill tone={RUN_TONE[t.lastRun.status]}>Son liste: {t.lastRun.statusLabel}</Pill>}
      </div>
      {p && (
        <div className="mt-2 rounded-xl bg-slate-50 p-2.5 text-[12px]">
          {p.info.aciklama && <p className="mb-1 text-canvas-muted">{p.info.aciklama}</p>}
          <div className="grid grid-cols-2 gap-1 sm:grid-cols-4">
            <span>Aday <strong className="font-mono tabular-nums">{fmtInt(p.candidates)}</strong></span>
            <span>Okura bağlı <strong className="font-mono tabular-nums">{fmtInt(p.linked)}</strong></span>
            <span>Ulaşılabilir <strong className="font-mono tabular-nums">{fmtInt(p.reachable)}</strong></span>
            <span>Hedef/kontrol <strong className="font-mono tabular-nums">{fmtInt(p.target)}/{fmtInt(p.control)}</strong></span>
          </div>
          {Object.keys(p.excluded).length > 0 && (
            <p className="mt-1 text-[11.5px] text-canvas-muted">
              Dışarıda: {Object.entries(p.excluded).map(([k, n]) => `${excl[k] ?? k} ${fmtInt(n)}`).join(' · ')}
            </p>
          )}
        </div>
      )}
      {canTrigger && (
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" className={btnGhost} onClick={onPreview} disabled={busy}>
            {busy && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}Önizle
          </button>
          <button type="button" className={btnPrimary} onClick={onRun} disabled={running}>
            {running ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Play aria-hidden className="h-4 w-4" />}Listeyi çalıştır
          </button>
          <button type="button" className={btnGhost} onClick={onArchive}>Arşive kaldır</button>
        </div>
      )}
    </Panel>
  );
}

function TriggerForm({ onDone }: { onDone: () => void }) {
  const meta = useMeta();
  const [name, setName] = useState('');
  const [kind, setKind] = useState<TriggerKind>('geri-kazanim');
  const [channel, setChannel] = useState<Channel>('email');
  const [share, setShare] = useState(String(meta.data?.settings.controlShare ?? 0.1));
  const [minGun, setMinGun] = useState('90');
  const [maxGun, setMaxGun] = useState('365');
  const [barkod, setBarkod] = useState('');
  const [duzey, setDuzey] = useState('alt');
  const books = useQuery({ queryKey: ['commerce', 'new-books'], queryFn: commerceApi.newBooks, enabled: ENGINE_ENABLED && kind === 'yeni-kitap' });
  const create = useMutation({
    mutationFn: () => commerceApi.createTrigger({
      name, kind, channel, controlShare: Number(share.replace(',', '.')),
      params: kind === 'yeni-kitap' ? { barkod, duzey } : { minGun: Number(minGun), maxGun: Number(maxGun) },
    }),
    onSuccess: () => { toast.success('Tetik kaydedildi.'); onDone(); },
    onError: (e) => toast.error(errText(e, 'Tetik kaydedilemedi.') ?? ''),
  });
  const kinds = meta.data?.kinds ?? { 'yeni-kitap': 'Yeni kitap', 'geri-kazanim': 'Geri kazanım', 'ikinci-siparis': 'İkinci sipariş', 'terk-sepeti': 'Terk sepeti' };
  return (
    <Panel>
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <label className="flex flex-col gap-1 sm:col-span-2"><span className={label}>Ad</span>
          <input className={field} value={name} onChange={(e) => setName(e.target.value)} placeholder="Örn. Ekim geri kazanım" required minLength={3} />
        </label>
        <label className="flex flex-col gap-1"><span className={label}>Tür</span>
          <select className={field} value={kind} onChange={(e) => {
            const k = e.target.value as TriggerKind;
            setKind(k);
            if (k === 'ikinci-siparis') { setMinGun('14'); setMaxGun('90'); }
            if (k === 'geri-kazanim') { setMinGun('90'); setMaxGun('365'); }
          }}>
            {(['geri-kazanim', 'ikinci-siparis', 'yeni-kitap'] as TriggerKind[]).map((k) => <option key={k} value={k}>{kinds[k]}</option>)}
            <option value="terk-sepeti" disabled>{kinds['terk-sepeti']} (sepet verisi yok)</option>
          </select>
        </label>
        <label className="flex flex-col gap-1"><span className={label}>Kanal</span>
          <select className={field} value={channel} onChange={(e) => setChannel(e.target.value as Channel)}>
            <option value="email">E-posta</option><option value="sms">SMS</option><option value="call">Arama</option>
          </select>
        </label>
        {kind === 'yeni-kitap' ? (
          <>
            <label className="flex flex-col gap-1 sm:col-span-2"><span className={label}>Yeni kitap</span>
              <select className={field} value={barkod} onChange={(e) => setBarkod(e.target.value)} required>
                <option value="">Seçin…</option>
                {(books.data?.items ?? []).map((b) => (
                  <option key={b.barkod} value={b.barkod} disabled={!b.dugum}>
                    {b.ad ?? b.barkod} · {fmtDay(b.acilis)}{b.dugumAdi ? ` · ${b.dugumAdi}` : ' · kategori yok'}
                  </option>
                ))}
              </select>
              {books.data?.not && <span className="text-[11.5px] text-amber-800">{books.data.not}</span>}
              {books.data && books.data.items.length === 0 && <span className="text-[11.5px] text-canvas-muted">Son {books.data.gun} günde açılmış barkodlu kitap yok.</span>}
            </label>
            <label className="flex flex-col gap-1"><span className={label}>Eşleşme düzeyi</span>
              <select className={field} value={duzey} onChange={(e) => setDuzey(e.target.value)}>
                <option value="yaprak">Aynı kategori</option><option value="altalt">Alt-alt kategori</option>
                <option value="alt">Alt kategori</option><option value="ana">Ana kategori</option>
              </select>
            </label>
          </>
        ) : (
          <>
            <label className="flex flex-col gap-1"><span className={label}>{kind === 'geri-kazanim' ? 'Son siparişten en az (gün)' : 'İlk siparişten en az (gün)'}</span>
              <input className={field} inputMode="numeric" value={minGun} onChange={(e) => setMinGun(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1"><span className={label}>En çok (gün)</span>
              <input className={field} inputMode="numeric" value={maxGun} onChange={(e) => setMaxGun(e.target.value)} />
            </label>
          </>
        )}
        <label className="flex flex-col gap-1"><span className={label}>Kontrol grubu payı (0–0,5)</span>
          <input className={field} inputMode="decimal" value={share} onChange={(e) => setShare(e.target.value)} />
        </label>
        <div className="flex flex-wrap items-end gap-2 sm:col-span-2">
          <button type="submit" className={btnPrimary} disabled={create.isPending}>{create.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}Kaydet</button>
          <button type="button" className={btnGhost} onClick={onDone}>Vazgeç</button>
        </div>
      </form>
    </Panel>
  );
}

function RunCard({ r, excl, onChange }: { r: Run; excl: Record<string, string>; onChange: () => void }) {
  const meta = useMeta();
  const me = meta.data?.me;
  const [note, setNote] = useState('');
  const [purpose, setPurpose] = useState('');
  const [campaign, setCampaign] = useState(false);
  const decide = useMutation({
    mutationFn: (approve: boolean) => (approve ? commerceApi.approve(r.id, note || undefined) : commerceApi.reject(r.id, note)),
    onSuccess: () => { setNote(''); onChange(); },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.') ?? ''),
  });
  const exp = useMutation({
    mutationFn: () => commerceApi.exportRun(r.id, purpose),
    onSuccess: (x) => { toast.success(`${fmtInt(x.count)} kişi indirildi; ${fmtInt(x.excluded)} kişi yeniden denetimde dışarıda kaldı.`); onChange(); },
    onError: (e) => toast.error(errText(e, 'Liste indirilemedi.') ?? ''),
  });
  const mine = me && [r.createdBy.toLowerCase()].includes(me.username.toLowerCase());
  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">{r.kindLabel} · {r.channelLabel}</div>
          <h3 className="text-[14px] font-extrabold">{r.triggerName}</h3>
          <p className="text-[11.5px] text-canvas-muted">{fmtDay(r.at)} · {r.createdBy}</p>
        </div>
        <Pill tone={RUN_TONE[r.status]}>{r.statusLabel}</Pill>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-1 text-[12px] sm:grid-cols-4">
        <span>Aday <strong className="font-mono tabular-nums">{fmtInt(r.candidates)}</strong></span>
        <span>Ulaşılabilir <strong className="font-mono tabular-nums">{fmtInt(r.reachable)}</strong></span>
        <span>Hedef <strong className="font-mono tabular-nums">{fmtInt(r.target)}</strong></span>
        <span>Kontrol <strong className="font-mono tabular-nums">{fmtInt(r.control)}</strong></span>
      </div>
      {Object.keys(r.excluded).length > 0 && (
        <p className="mt-1 text-[11.5px] text-canvas-muted">Dışarıda: {Object.entries(r.excluded).map(([k, n]) => `${excl[k] ?? k} ${fmtInt(n)}`).join(' · ')}</p>
      )}
      {r.decisionNote && <p className="mt-1 text-[11.5px]">Karar notu: {r.decisionNote} ({r.approvedBy})</p>}
      {r.exportedAt && <p className="mt-1 text-[11.5px] text-canvas-muted">{fmtDay(r.exportedAt)} tarihinde {r.exportedBy} {fmtInt(r.exportedCount)} kişiyi indirdi.</p>}

      {r.status === 'onay-bekliyor' && me?.canApprove && !mine && (
        <div className="mt-3 flex flex-col gap-2">
          <input className={field} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Not (geri göndermede zorunlu)" />
          <div className="flex flex-wrap gap-2">
            <button type="button" className={btnPrimary} onClick={() => decide.mutate(true)} disabled={decide.isPending}>Onayla</button>
            <button type="button" className={btnGhost} onClick={() => decide.mutate(false)} disabled={decide.isPending || !note.trim()}>Geri gönder</button>
          </div>
        </div>
      )}
      {(r.status === 'onayli' || r.status === 'aktarildi') && (
        <div className="mt-3 flex flex-col gap-2">
          {me?.canList && meta.data?.exportEnabled && (
            <div className="flex flex-col gap-2 sm:flex-row">
              <input className={field} value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="Amaç (kayda geçer), örn. Ekim bülteni" />
              <button type="button" className={btnGhost} onClick={() => exp.mutate()} disabled={exp.isPending || purpose.trim().length < 5}>
                {exp.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}Hedef grubu indir
              </button>
            </div>
          )}
          {me?.canTrigger && (campaign ? <CampaignForm run={r} onDone={() => { setCampaign(false); onChange(); }} /> : (
            <button type="button" className={`${btnGhost} self-start`} onClick={() => setCampaign(true)} disabled={r.control === 0}>
              Kampanya sonucu için aç{r.control === 0 ? ' (kontrol grubu yok)' : ''}
            </button>
          ))}
        </div>
      )}
      <p className="mt-2 text-[11px] text-canvas-muted">Kontrol grubu hiçbir zaman indirilmez; sonuç ölçümü içindir.</p>
    </Panel>
  );
}

function CampaignForm({ run, onDone }: { run: Run; onDone: () => void }) {
  const today = new Date().toISOString().slice(0, 10);
  const [name, setName] = useState(run.triggerName ?? '');
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState('');
  const create = useMutation({
    mutationFn: () => commerceApi.createCampaign({ runId: run.id, name, start, end: end || undefined }),
    onSuccess: () => { toast.success('Kampanya açıldı; sonuç her gece hesaplanır.'); onDone(); },
    onError: (e) => toast.error(errText(e, 'Kampanya açılamadı.') ?? ''),
  });
  return (
    <form className="grid gap-2 rounded-xl bg-slate-50 p-2.5 sm:grid-cols-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
      <label className="flex flex-col gap-1 sm:col-span-3"><span className={label}>Kampanya adı</span>
        <input className={field} value={name} onChange={(e) => setName(e.target.value)} required minLength={3} />
      </label>
      <label className="flex flex-col gap-1"><span className={label}>Başlangıç</span><input type="date" className={field} value={start} onChange={(e) => setStart(e.target.value)} /></label>
      <label className="flex flex-col gap-1"><span className={label}>Bitiş (boşsa ayardaki pencere)</span><input type="date" className={field} value={end} onChange={(e) => setEnd(e.target.value)} /></label>
      <div className="flex items-end gap-2">
        <button type="submit" className={btnPrimary} disabled={create.isPending}>Aç</button>
        <Link to={`${ROOT}/kampanyalar`} className={btnGhost}>Sonuçlar</Link>
      </div>
    </form>
  );
}
