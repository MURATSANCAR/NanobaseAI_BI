import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Plus, RotateCcw } from 'lucide-react';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import { fmtDay } from '../api';
import { Block } from '../parts';
import { dLabel, launchApi, type Launch, type LaunchMeta, type LaunchTask } from './api';

/** Kontrol listesi: planın takvimi + lansman maddeleri, yayın gününe göre üç bölüm. Tek tıkla «yapıldı»; kanıt
 *  bağlantısı ve sorumlu satırın altında. Gönderi günü maddesinde planın onaylı metni açılır (telefondan kopyalamak için);
 *  yayını kişi yapar, portal dış kanala göndermez. */

const PHASES: Array<{ key: string; title: string; test: (g: number) => boolean }> = [
  { key: 'once', title: 'Yayından önce', test: (g) => g < 0 },
  { key: 'hafta', title: 'Yayın haftası', test: (g) => g >= 0 && g < 7 },
  { key: 'ay', title: 'İlk ay', test: (g) => g >= 7 },
];

function Row({ t, launch, meta, canWrite }: { t: LaunchTask; launch: Launch; meta: LaunchMeta; canWrite: boolean }) {
  const qc = useQueryClient();
  const [url, setUrl] = useState(t.kanitUrl ?? '');
  const [owner, setOwner] = useState(t.sorumlu ?? '');
  const today = new Date().toISOString().slice(0, 10);
  const late = t.durum === 'bekliyor' && !!t.tarih && t.tarih < today;
  const mat = t.materyalTur ? launch.materials.find((m) => m.tur === t.materyalTur) : undefined;
  const save = useMutation({
    mutationFn: (b: { durum?: string; kanitUrl?: string | null; sorumlu?: string | null }) => launchApi.task(launch.id, t.id ?? '', b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['launch'] }),
    onError: (e) => toast.error(errText(e, 'Madde kaydedilemedi.') ?? ''),
  });
  const done = t.durum === 'yapildi';
  return (
    <li className={`rounded-2xl border p-2.5 ${late ? 'border-red-200 bg-red-50/60' : done ? 'border-emerald-100 bg-emerald-50/40' : 'border-slate-100 bg-white/80'}`}>
      <div className="flex items-start gap-2.5">
        {canWrite ? (
          <button type="button" aria-pressed={done} aria-label={done ? 'Bekliyor olarak geri al' : 'Yapıldı olarak işaretle'}
            disabled={save.isPending} onClick={() => save.mutate({ durum: done ? 'bekliyor' : 'yapildi' })}
            className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border transition-[transform,background-color] duration-150 ease-out active:scale-[0.97] ${done ? 'border-emerald-600 bg-emerald-600 text-white' : 'border-slate-300 bg-white text-canvas-muted'}`}>
            {done ? <Check aria-hidden className="h-5 w-5" /> : <span className="h-3 w-3 rounded-sm border-2 border-slate-300" aria-hidden />}
          </button>
        ) : (
          <Pill tone={done ? 'ok' : late ? 'err' : 'muted'}>{meta.taskStatuses[t.durum]}</Pill>
        )}
        <div className="min-w-0 flex-1">
          <div className={`break-words text-[13px] font-semibold leading-snug ${done ? 'text-canvas-muted line-through decoration-slate-300' : ''}`}>{t.is}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-canvas-muted">
            <span className="font-mono font-bold tabular-nums text-canvas-ink">{dLabel(t.gunFarki)}</span>
            <span>{fmtDay(t.tarih)}</span>
            {late && <Pill tone="err">Gecikti</Pill>}
            {t.durum === 'atlandi' && <Pill tone="muted">Atlandı</Pill>}
            {t.kanal && <Pill tone="muted">{meta.channels[t.kanal] ?? t.kanal}</Pill>}
            {t.kaynak === 'lansman' && <Pill tone="violet">Lansman</Pill>}
            <span>· {t.sorumlu ?? `${launch.sahip ?? '—'} (lansman sahibi)`}</span>
            {t.kanitUrl && (
              <a href={t.kanitUrl} target="_blank" rel="noreferrer noopener" className="inline-flex min-h-8 items-center font-bold text-canvas-violet hover:underline">Kanıt</a>
            )}
          </div>
          {mat && (
            <details className="mt-1.5">
              <summary className="inline-flex min-h-8 cursor-pointer items-center text-[11.5px] font-bold text-canvas-violet">Onaylı metin: {mat.turAdi}</summary>
              <p className="mt-1 whitespace-pre-line rounded-xl bg-white/80 p-2 text-[12px] leading-snug">{mat.metin}</p>
            </details>
          )}
          {canWrite && (
            <details className="mt-1">
              <summary className="inline-flex min-h-8 cursor-pointer items-center text-[11.5px] font-bold text-canvas-muted">Kanıt, sorumlu, atla</summary>
              <div className="mt-1.5 grid grid-cols-1 gap-2 sm:grid-cols-[1fr_180px_auto] sm:items-end">
                <label className="flex min-w-0 flex-col gap-1">
                  <span className={labelCls}>Kanıt bağlantısı</span>
                  <input className={field} inputMode="url" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={labelCls}>Sorumlu (AD hesabı)</span>
                  <input className={field} value={owner} onChange={(e) => setOwner(e.target.value)} />
                </label>
                <div className="flex gap-2">
                  <button type="button" className={btnPrimary} disabled={save.isPending}
                    onClick={() => save.mutate({ kanitUrl: url.trim() || null, sorumlu: owner.trim() || null }, { onSuccess: () => toast.success('Kaydedildi.') })}>
                    Kaydet
                  </button>
                  {t.durum !== 'atlandi' ? (
                    <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate({ durum: 'atlandi' })}>Atla</button>
                  ) : (
                    <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate({ durum: 'bekliyor' })}>
                      <RotateCcw aria-hidden className="h-4 w-4" />Geri al
                    </button>
                  )}
                </div>
              </div>
            </details>
          )}
        </div>
      </div>
    </li>
  );
}

export default function ChecklistTab({ launch, meta }: { launch: Launch; meta: LaunchMeta }) {
  const qc = useQueryClient();
  const canWrite = meta.me.canWrite;
  const [add, setAdd] = useState({ is: '', tarih: new Date().toISOString().slice(0, 10), sorumlu: '' });
  const create = useMutation({
    mutationFn: () => launchApi.addTask(launch.id, { is: add.is, tarih: add.tarih, sorumlu: add.sorumlu || undefined }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['launch'] }); setAdd((a) => ({ ...a, is: '' })); toast.success('Madde eklendi.'); },
    onError: (e) => toast.error(errText(e, 'Madde eklenemedi.') ?? ''),
  });
  const total = launch.tasks.length;
  const doneN = launch.tasks.filter((t) => t.durum === 'yapildi').length;
  return (
    <Block
      title="Kontrol listesi"
      help={`${doneN} / ${total} madde yapıldı. Maddeler pazarlama planının takvimiyle aynı kayıttır: burada işaretlenen planda da yapılmış görünür. Yayın günü değişince bekleyen şablon maddeleri kayar.`}
    >
      {total === 0 && <Note tone="info">Kontrol listesinde madde yok.</Note>}
      <div className="flex flex-col gap-3">
        {PHASES.map((ph) => {
          const rows = launch.tasks.filter((t) => ph.test(t.gunFarki ?? 0));
          if (!rows.length) return null;
          return (
            <section key={ph.key}>
              <h3 className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                {ph.title} · {rows.filter((t) => t.durum === 'yapildi').length}/{rows.length}
              </h3>
              <ol className="flex flex-col gap-1.5">
                {rows.map((t) => <Row key={t.id} t={t} launch={launch} meta={meta} canWrite={canWrite} />)}
              </ol>
            </section>
          );
        })}
      </div>
      {canWrite && (
        <form className="mt-3 grid grid-cols-1 gap-2 rounded-2xl bg-slate-50 p-2.5 sm:grid-cols-[1fr_160px_160px_auto] sm:items-end"
          onSubmit={(e) => { e.preventDefault(); if (add.is.trim()) create.mutate(); }}>
          <label className="flex min-w-0 flex-col gap-1">
            <span className={labelCls}>Yeni madde</span>
            <input className={field} value={add.is} placeholder="Ör. Yazarla canlı yayın saatini kesinleştir" onChange={(e) => setAdd({ ...add, is: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tarih</span>
            <input type="date" className={field} value={add.tarih} onChange={(e) => setAdd({ ...add, tarih: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Sorumlu</span>
            <input className={field} value={add.sorumlu} onChange={(e) => setAdd({ ...add, sorumlu: e.target.value })} />
          </label>
          <button type="submit" className={btnGhost} disabled={!add.is.trim() || create.isPending}><Plus aria-hidden className="h-4 w-4" />Ekle</button>
        </form>
      )}
    </Block>
  );
}
