import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, RotateCcw, Save, Send } from 'lucide-react';
import { adminApi, type AdminSetting } from '../engine';
import { Card, Loading, Note, Pill, Section, btnGhost, btnPrimary, errText, field, fmtDate } from './ui';

const SOURCE: Record<AdminSetting['source'], string> = {
  screen: 'Bu ekrandan',
  env: 'Sunucu ayar dosyası',
  default: 'Varsayılan',
};

function Field({ s, value, onChange, onReset, resetting }: {
  s: AdminSetting;
  value: string;
  onChange: (v: string) => void;
  onReset: () => void;
  resetting: boolean;
}) {
  const id = `set-${s.key}`;
  return (
    <div className="grid gap-1.5 py-3 sm:grid-cols-[220px_1fr] sm:gap-4">
      <div className="min-w-0">
        <label htmlFor={id} className="text-[12.5px] font-bold">
          {s.label}
        </label>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-canvas-muted">
          <Pill tone={s.source === 'screen' ? 'violet' : 'muted'}>{SOURCE[s.source]}</Pill>
          {s.source === 'screen' && s.updatedBy && (
            <span>
              {s.updatedBy} · {fmtDate(s.updatedAt)}
            </span>
          )}
        </div>
      </div>
      <div className="min-w-0">
        {s.type === 'bool' ? (
          <label className="flex min-h-11 cursor-pointer items-center gap-2 sm:min-h-0">
            <input id={id} type="checkbox" checked={value === '1'} onChange={(e) => onChange(e.target.checked ? '1' : '0')} className="h-4 w-4 accent-[#7c5cff]" />
            <span className="text-[12.5px] font-semibold">{value === '1' ? 'Açık' : 'Kapalı'}</span>
          </label>
        ) : (
          <input
            id={id}
            type={s.type === 'secret' ? 'password' : s.type === 'int' ? 'number' : 'text'}
            pattern={s.type === 'time' ? '([01][0-9]|2[0-4]):[0-5][0-9]' : undefined}
            inputMode={s.type === 'int' ? 'numeric' : undefined}
            min={s.type === 'int' ? 0 : undefined}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={s.type === 'secret' ? (s.hasValue ? '•••••••• (kayıtlı; değiştirmek için yazın)' : 'Girilmedi') : s.type === 'time' ? '08:00' : ''}
            autoComplete={s.type === 'secret' ? 'new-password' : 'off'}
            autoCapitalize="none"
            spellCheck={false}
            className={field}
          />
        )}
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
          {s.help && <span className="text-[11.5px] text-canvas-muted">{s.help}</span>}
          {s.source === 'screen' && s.key !== 'TIMAS_ADMIN_USERS' && (
            <button type="button" onClick={onReset} disabled={resetting} className="inline-flex min-h-11 items-center gap-1 text-[11.5px] font-bold text-canvas-muted hover:text-canvas-ink sm:min-h-0">
              <RotateCcw className="h-3 w-3" />
              Sunucu değerine dön
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function SettingsPanel() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['admin', 'settings'], queryFn: adminApi.settings, retry: false });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [testTo, setTestTo] = useState('');
  const [saved, setSaved] = useState<string | null>(null);

  const initial = useMemo(() => {
    const o: Record<string, string> = {};
    q.data?.items.forEach((s) => (o[s.key] = s.type === 'secret' ? '' : (s.value ?? '')));
    return o;
  }, [q.data]);
  useEffect(() => setDraft(initial), [initial]);

  const dirty = Object.keys(draft).filter((k) => draft[k] !== initial[k]);
  const apply = (data: unknown) => {
    qc.setQueryData(['admin', 'settings'], data);
    void qc.invalidateQueries({ queryKey: ['admin', 'overview'] });
  };

  const save = useMutation({
    mutationFn: () => adminApi.saveSettings(Object.fromEntries(dirty.map((k) => [k, draft[k]]))),
    onSuccess: (d) => {
      apply(d);
      setSaved(d.changed.length ? `${d.changed.length} ayar kaydedildi.` : 'Değişen bir şey yoktu.');
      window.setTimeout(() => setSaved(null), 3000);
    },
  });
  const reset = useMutation({ mutationFn: (key: string) => adminApi.resetSetting(key), onSuccess: apply });
  const test = useMutation({ mutationFn: (to: string) => adminApi.testEmail(to) });

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <Note tone="err">{errText(q.error, 'Ayarlar okunamadı.')}</Note>;

  return (
    <div className="space-y-5 pb-20">
      <Section
        title="Ayarlar"
        help="Burada kaydedilen değer sunucu ayar dosyasındakinin önüne geçer. Her değişiklik kişi ve saatle değişiklik kaydına yazılır; parolalar kayda da ekrana da geri gelmez."
      />
      {q.data.groups.map((g) => (
        <Card key={g.id}>
          <div className="text-[14px] font-extrabold">{g.label}</div>
          <p className="text-[12px] text-canvas-muted">{g.help}</p>
          <div className="mt-1 divide-y divide-slate-100">
            {q.data.items
              .filter((s) => s.group === g.id)
              .map((s) => (
                <Field
                  key={s.key}
                  s={s}
                  value={draft[s.key] ?? ''}
                  onChange={(v) => setDraft((d) => ({ ...d, [s.key]: v }))}
                  onReset={() => reset.mutate(s.key)}
                  resetting={reset.isPending}
                />
              ))}
          </div>
          {g.id === 'email' && (
            <div className="mt-2 rounded-xl bg-slate-50 p-3">
              <div className="text-[12.5px] font-bold">Deneme e-postası</div>
              <p className="text-[11.5px] text-canvas-muted">Kaydedilmiş ayarla gönderir. Önce değişiklikleri kaydedin.</p>
              <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                <input value={testTo} onChange={(e) => setTestTo(e.target.value)} placeholder="ad@timas.com.tr" autoCapitalize="none" spellCheck={false} className={field} />
                <button type="button" disabled={!testTo.includes('@') || test.isPending || dirty.length > 0} onClick={() => test.mutate(testTo.trim())} className={`${btnGhost} shrink-0`}>
                  {test.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  Gönder
                </button>
              </div>
              {test.data && <div className="mt-2"><Note tone={test.data.ok ? 'ok' : 'err'}>{test.data.message}</Note></div>}
              {test.error && <div className="mt-2"><Note tone="err">{errText(test.error, 'Deneme gönderilemedi.')}</Note></div>}
            </div>
          )}
        </Card>
      ))}

      {/* Kaydet çubuğu: yalnız değişiklik varken görünür */}
      <div
        className={[
          'sticky bottom-2 z-10 flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-canvas-card backdrop-blur transition-[opacity,transform] duration-200 ease-out motion-reduce:transition-none',
          dirty.length || save.error || saved ? 'translate-y-0 opacity-100' : 'pointer-events-none translate-y-2 opacity-0',
        ].join(' ')}
      >
        <div className="min-w-0 text-[12.5px] font-semibold">
          {save.error ? (
            <span className="text-red-700">{errText(save.error, 'Kaydedilemedi.')}</span>
          ) : saved ? (
            <span className="text-emerald-700">{saved}</span>
          ) : (
            `${dirty.length} değişiklik kaydedilmedi`
          )}
        </div>
        <div className="flex gap-2">
          <button type="button" disabled={!dirty.length} onClick={() => setDraft(initial)} className={btnGhost}>
            Vazgeç
          </button>
          <button type="button" disabled={!dirty.length || save.isPending} onClick={() => save.mutate()} className={btnPrimary}>
            {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Kaydet
          </button>
        </div>
      </div>
    </div>
  );
}
