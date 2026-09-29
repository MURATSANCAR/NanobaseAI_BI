import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Play } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, btnGhost, errText } from '../admin/ui';
import { mqApi } from './api';
import { MqFrame, Tabs } from './parts';
import Scorecard from './Scorecard';
import Runs from './Runs';
import ClassBoard from './ClassBoard';
import FeedbackQueue from './FeedbackQueue';
import Versions from './Versions';

/** M50 Zeki AI kalitesi: Karne · Koşular · Hata sınıfları · Geri bildirim · Sürümler.
 *  Sekme ve seçili koşu adres çubuğunda (?sekme=, ?kosu=, ?sinif=); bağlantı paylaşılabilir. */

const TABS = [
  { key: 'karne', label: 'Karne' },
  { key: 'kosular', label: 'Koşular' },
  { key: 'siniflar', label: 'Hata sınıfları' },
  { key: 'geri-bildirim', label: 'Geri bildirim' },
  { key: 'surumler', label: 'Sürümler' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function ModelQualityScreen() {
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ['mq', 'meta'], queryFn: mqApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'karne') as Tab;
  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );
  const queue = useQuery({
    queryKey: ['mq', 'queue', 'badge'],
    queryFn: () => mqApi.queue({ state: 'yeni', verdict: 'kismen,yanlis' }),
    enabled: ENGINE_ENABLED && !!meta.data,
    staleTime: 60_000,
  });
  const tabs = TABS.map((t) => (t.key === 'geri-bildirim' ? { ...t, badge: queue.data?.total || null } : t));

  return (
    <MqFrame aside={meta.data?.me.canRun ? <StartRuns suites={meta.data.suites} startable={meta.data.startable} onStarted={() => update({ sekme: 'kosular', kosu: null })} /> : undefined}>
      {!ENGINE_ENABLED && <Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Ekran bilgisi okunamadı.')}</Note>}
      <Tabs tabs={tabs} value={tab} onChange={(t) => update({ sekme: t === 'karne' ? null : t, kosu: null, sinif: null })} />
      {meta.data && tab === 'karne' && <Scorecard meta={meta.data} onOpenRun={(id) => update({ sekme: 'kosular', kosu: id })} />}
      {meta.data && tab === 'kosular' && <Runs meta={meta.data} selected={params.get('kosu')} onSelect={(id) => update({ kosu: id })} />}
      {meta.data && tab === 'siniflar' && <ClassBoard meta={meta.data} selected={params.get('sinif')} onSelect={(k) => update({ sinif: k })} />}
      {meta.data && tab === 'geri-bildirim' && <FeedbackQueue meta={meta.data} />}
      {meta.data && tab === 'surumler' && <Versions />}
    </MqFrame>
  );
}

function StartRuns({ suites, startable, onStarted }: { suites: Record<string, string>; startable: string[]; onStarted: () => void }) {
  const qc = useQueryClient();
  const start = useMutation({
    mutationFn: (suite: string) => mqApi.start(suite),
    onSuccess: (r) => {
      toast.success(`${r.suiteLabel} sıraya alındı; birkaç dakika içinde başlar.`);
      void qc.invalidateQueries({ queryKey: ['mq'] });
      onStarted();
    },
    onError: (e) => toast.error(errText(e, 'Koşu başlatılamadı.') ?? 'Koşu başlatılamadı.'),
  });
  const help: Record<string, string> = {
    resolver: 'Zeki AI soruları önceki ölçümdeki gibi anlıyor mu · yaklaşık 2 dk, kullanıcıları yavaşlatmaz',
    answer: 'Doğrulanmış sorular doğru rakamla cevaplanıyor mu · yaklaşık 35 dk, bu sürede Zeki AI biraz yavaşlayabilir',
  };
  return (
    <div className="flex flex-col gap-2 rounded-2xl bg-white/70 p-3">
      <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Koşu başlat</div>
      {startable.map((s) => (
        <button key={s} type="button" disabled={start.isPending} onClick={() => start.mutate(s)} className={`${btnGhost} !justify-start text-left`}>
          <Play aria-hidden className="h-4 w-4 shrink-0" />
          <span className="flex min-w-0 flex-col">
            <span>{suites[s] ?? s}</span>
            <span className="text-[11px] font-semibold text-canvas-muted">{help[s]}</span>
          </span>
        </button>
      ))}
    </div>
  );
}
