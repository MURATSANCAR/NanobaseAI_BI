import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Plug, RotateCcw, Save, Search, Send, X } from 'lucide-react';
import { adminApi, type AdminCheck, type AdminSetting, type AdminSettings } from '../engine';
import { Card, Loading, Note, Pill, Section, btnGhost, btnPrimary, errText, field, fmtDate } from './ui';
import { categorize, pickCategory, searchSettings } from './settingsCategories';

/** Ayarlar ve Yönetim ekranının sol menüsü aynı sorguyu paylaşır (kategoriler oradan da okunur). */
export const settingsQuery = { queryKey: ['admin', 'settings'] as const, queryFn: adminApi.settings, retry: false } as const;

/** Hangi grubun altında hangi deneme düğmesi çıkar. */
const GROUP_CHECK: Record<string, { id: string; label: string; help: string }> = {
  database: {
    id: 'database',
    label: 'Bağlan',
    help: 'Kaydedilmiş ayarla Logo veritabanına bağlanır ve hangi veritabanına, hangi hesapla bağlandığını söyler.',
  },
  crm: {
    id: 'crm',
    label: 'Bağlan',
    help: 'CRM ayrı bir bağlantı değil: aynı sunucudaki başka bir veritabanı. Deneme, o veritabanının okunabildiğine bakar.',
  },
  llm: { id: 'llm', label: 'Sor', help: 'Modele tek kelimelik bir soru sorar; cevabın süresini ve geldiğini gösterir.' },
  seo: {
    id: 'seo',
    label: 'Bağlantıyı sına',
    help: 'T-soft’a kaydedilen kullanıcıyla giriş yapar, bir ürün okur; servis hesabı girildiyse Search Console’dan son 7 günü sorar. Hiçbir şey yazmaz.',
  },
  geo: {
    id: 'geo',
    label: 'Bağlantıyı sına',
    help: 'Girilmiş her yapay zekâ anahtarını hesabın model listesini okuyarak dener. Soru sormaz, kota harcamaz.',
  },
  mailbox: {
    id: 'mailbox',
    label: 'Kutuyu oku',
    help: 'Kaydedilmiş bağlantıyla kutunun ileti sayısını ve etiket listesini okur. Hiçbir ileti göndermez, değiştirmez.',
  },
};

/** Sınama sonucu: üstte yeşil «Başarılı» ya da kırmızı «Hata», altında varsa bağlantı bağlantı satırlar. */
function CheckResult({ r }: { r: AdminCheck }) {
  const tone = { ok: 'ok', err: 'err', off: 'muted' } as const;
  const word = { ok: 'Başarılı', err: 'Hata', off: 'Girilmemiş' } as const;
  return (
    <div className="mt-2 space-y-1.5" aria-live="polite">
      <div
        className={`flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-xl px-3 py-2 text-[12px] font-semibold ${
          r.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'
        }`}
      >
        <span className="font-extrabold">{r.ok ? '✓ Başarılı' : '✕ Hata'}</span>
        <span className="min-w-0 flex-1 break-words">{r.message}</span>
        <span className="shrink-0 text-[11px] font-normal opacity-80">{fmtDate(r.at)}{r.ms ? ` · ${r.ms} ms` : ''}</span>
      </div>
      {r.parts && (
        <ul className="space-y-1">
          {r.parts.map((p) => (
            <li key={p.label} className="flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-xl bg-white px-3 py-1.5">
              <Pill tone={tone[p.state]}>{word[p.state]}</Pill>
              <span className="text-[12px] font-bold">{p.label}</span>
              <span className="min-w-0 flex-1 break-words text-[11.5px] text-canvas-muted">{p.message}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const SOURCE: Record<AdminSetting['source'], string> = {
  screen: 'Bu ekrandan',
  env: 'Sunucu ayar dosyası',
  file: 'Bağlantı dosyası',
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

/** Ayar kategorileri (ikinci düzey gezinme): masaüstünde Yönetim menüsünde «Ayarlar»ın altında, telefonda
 *  ekranın üstünde yatay kayan çipler. Seçim adres çubuğunda (`?bolum=settings&kategori=…`). */
export function SettingsCategoryNav({ data, variant, onPick }: { data: AdminSettings; variant: 'chips' | 'list'; onPick?: () => void }) {
  const [params, setParams] = useSearchParams();
  const cats = categorize(data);
  const current = pickCategory(cats, params.get('kategori'));
  const go = (id: string) => {
    setParams({ bolum: 'settings', kategori: id });
    onPick?.();
  };
  if (variant === 'chips') {
    return (
      <nav aria-label="Ayar kategorileri" className="-mx-1 md:hidden">
        <ul className="flex gap-1.5 overflow-x-auto px-1 pb-1 [scrollbar-width:none]">
          {cats.map((c) => {
            const on = c.id === current?.id;
            return (
              <li key={c.id} className="shrink-0">
                <button
                  type="button"
                  onClick={() => go(c.id)}
                  aria-current={on ? 'page' : undefined}
                  className={`min-h-11 whitespace-nowrap rounded-full px-3.5 text-[12.5px] font-bold transition-colors ${on ? 'bg-canvas-ink text-white' : 'bg-slate-100 text-canvas-ink'}`}
                >
                  {c.label}
                  <span className={`ml-1.5 text-[11px] tabular-nums ${on ? 'text-white/70' : 'text-canvas-muted'}`}>{c.groups.length}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
    );
  }
  return (
    <ul aria-label="Ayar kategorileri" className="mt-0.5 space-y-0.5 border-l border-slate-200 pl-2">
      {cats.map((c) => {
        const on = c.id === current?.id;
        return (
          <li key={c.id}>
            <button
              type="button"
              onClick={() => go(c.id)}
              aria-current={on ? 'page' : undefined}
              className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[12px] font-semibold transition-colors ${
                on ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted hover:bg-white/70 hover:text-canvas-ink'
              }`}
            >
              <span className="min-w-0 flex-1 truncate">{c.label}</span>
              <span className="text-[11px] font-bold tabular-nums text-canvas-muted">{c.groups.length}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export default function SettingsPanel() {
  const qc = useQueryClient();
  const q = useQuery(settingsQuery);
  const [params] = useSearchParams();
  const [query, setQuery] = useState('');
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [testTo, setTestTo] = useState('');
  const [saved, setSaved] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);

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
      const applied = d.applied?.length ? ` ${d.applied.join(' ve ')} yeniden kuruldu.` : '';
      setSaved(d.changed.length ? `${d.changed.length} ayar kaydedildi.${applied}` : 'Değişen bir şey yoktu.');
      setApplyError(d.applyError ?? null);
      window.setTimeout(() => setSaved(null), 6000);
    },
  });
  const reset = useMutation({ mutationFn: (key: string) => adminApi.resetSetting(key), onSuccess: apply });
  const test = useMutation({ mutationFn: (to: string) => adminApi.testEmail(to) });
  const [dirUser, setDirUser] = useState('');
  const dirTest = useMutation({ mutationFn: (u: string) => adminApi.testDirectory(u) });

  // Deneme sonuçları kimliğine göre durur: bir grubun sonucu, başka bir grup denenince silinmez.
  const [result, setResult] = useState<Record<string, AdminCheck>>({});
  const [checking, setChecking] = useState<string | null>(null);
  const keep = (items: AdminCheck[]) => setResult((r) => ({ ...r, ...Object.fromEntries(items.map((i) => [i.id, i])) }));
  const check = useMutation({
    mutationFn: (id: string) => {
      setChecking(id);
      return adminApi.test(id);
    },
    onSuccess: (d) => keep([d]),
    // İstek hiç cevap vermezse de (ağ, yetki, zaman aşımı) sonuç kırmızı görünür; tuş sessiz kalmaz.
    onError: (e, id) =>
      keep([{ id, group: null, label: '', ok: false, message: errText(e, 'Deneme yapılamadı.') ?? 'Deneme yapılamadı.', ms: 0, at: new Date().toISOString() }]),
    onSettled: () => setChecking(null),
  });
  // Kaydedilmemiş değişiklik varken tuş önce kaydeder, sonra sınar: deneme her zaman kayıtlı ayarla yapılır.
  const saveAndCheck = async (id: string) => {
    if (dirty.length) {
      setChecking(id);
      try {
        await save.mutateAsync();
      } catch {
        setChecking(null);
        return;
      }
    }
    check.mutate(id);
  };
  const checkAll = useMutation({ mutationFn: () => adminApi.testAll(), onSuccess: (d) => keep(d.items) });
  const system = useQuery({ queryKey: ['admin', 'system'], queryFn: adminApi.system, retry: false });

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <Note tone="err">{errText(q.error, 'Ayarlar okunamadı.')}</Note>;

  const data = q.data;
  const cats = categorize(data);
  const current = pickCategory(cats, params.get('kategori'));
  const searching = query.trim().length > 0;
  const hits = searching ? searchSettings(data, query) : [];
  // Gösterilecek gruplar: aramada tutanlar (yalnız tutan ayarlarıyla), yoksa seçili kategorinin grupları.
  const shown: Array<{ g: AdminSettings['groups'][number]; keys: string[] | 'all'; where?: string }> = searching
    ? hits.map((h) => ({ g: h.group, keys: h.keys, where: h.category.label }))
    : (current?.groups ?? []).map((g) => ({ g, keys: 'all' as const }));
  const hitCount = hits.reduce((n, h) => n + (h.keys === 'all' ? data.items.filter((s) => s.group === h.group.id).length : h.keys.length), 0);
  // Kaydedilmemiş değişiklik hangi kategorilerde: kaydet çubuğunda yazar (başka kategoride kalan değişiklik gözden kaçmasın).
  const groupCat = new Map(cats.flatMap((c) => c.groups.map((g) => [g.id, c.label] as const)));
  const dirtyCats = [...new Set(dirty.map((k) => groupCat.get(data.items.find((s) => s.key === k)?.group ?? '')).filter(Boolean))];

  return (
    <div className="space-y-5 pb-20">
      <Section
        title="Ayarlar"
        help="Burada kaydedilen değer sunucu ayar dosyasındakinin önüne geçer. Her değişiklik kişi ve saatle değişiklik kaydına yazılır; parolalar kayda da ekrana da geri gelmez."
        action={
          <button type="button" disabled={checkAll.isPending || dirty.length > 0} onClick={() => checkAll.mutate()} className={btnGhost}>
            {checkAll.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plug className="h-4 w-4" />}
            Tüm bağlantıları dene
          </button>
        }
      />
      {(checkAll.data || checkAll.error) && (
        <Card>
          <div className="text-[14px] font-extrabold">Bağlantı denemeleri</div>
          <p className="text-[12px] text-canvas-muted">
            Kaydedilmiş ayarla, gerçek bağlantı kurularak denendi. E-posta burada yalnız ayarın tamlığına bakar; gerçek gönderim için aşağıdaki deneme e-postasını kullanın.
          </p>
          {checkAll.error ? (
            <div className="mt-2"><Note tone="err">{errText(checkAll.error, 'Denemeler yapılamadı.')}</Note></div>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {checkAll.data?.items.map((c) => (
                <li key={c.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-xl bg-slate-50 px-3 py-2">
                  <Pill tone={c.ok ? 'ok' : 'err'}>{c.ok ? 'Bağlandı' : 'Bağlanamadı'}</Pill>
                  <span className="text-[12.5px] font-bold">{c.label}</span>
                  <span className="min-w-0 flex-1 break-words text-[11.5px] text-canvas-muted">{c.message}</span>
                  <span className="shrink-0 text-[11px] text-canvas-muted">{c.ms} ms</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
      <div className="space-y-2">
        <label className="relative block">
          <span className="sr-only">Ayar ara</span>
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && setQuery('')}
            placeholder="Ayar ara: grup, ayar adı ya da anahtarı"
            autoCapitalize="none"
            spellCheck={false}
            className={`${field} !pl-9 !pr-10`}
          />
          {searching && (
            <button
              type="button"
              onClick={() => setQuery('')}
              aria-label="Aramayı temizle"
              className="absolute right-1 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-lg text-canvas-muted hover:text-canvas-ink"
            >
              <X aria-hidden className="h-4 w-4" />
            </button>
          )}
        </label>
        {!searching && <SettingsCategoryNav data={data} variant="chips" />}
        <p className="text-[12px] text-canvas-muted" aria-live="polite">
          {searching
            ? hits.length
              ? `${hits.length} grupta ${hitCount} ayar bulundu.`
              : 'Eşleşen ayar yok. Grup adını, ayarın adını ya da anahtarını (ör. SMTP_HOST) deneyin.'
            : current
              ? `${current.label} · ${current.groups.length} grup`
              : ''}
        </p>
      </div>
      {applyError && <Note tone="warn">{applyError}</Note>}
      {shown.map(({ g, keys, where }) => (
        <Card key={g.id}>
          {where && <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">{where}</div>}
          <div className="text-[14px] font-extrabold">{g.label}</div>
          <p className="text-[12px] text-canvas-muted">{g.help}</p>
          <div className="mt-1 divide-y divide-slate-100">
            {data.items
              .filter((s) => s.group === g.id && (keys === 'all' || keys.includes(s.key)))
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
          {g.id === 'directory' && (
            <div className="mt-2 rounded-xl bg-slate-50 p-3">
              <div className="text-[12.5px] font-bold">Bağlantı denemesi</div>
              <p className="text-[11.5px] text-canvas-muted">
                Kaydedilmiş ayarla servis hesabı dizine bağlanır. Bir hesap adı yazarsanız onu da arar; boşsa servis hesabını arar. Önce değişiklikleri kaydedin.
              </p>
              <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                <input value={dirUser} onChange={(e) => setDirUser(e.target.value)} placeholder="hesap adı (isteğe bağlı)" autoCapitalize="none" spellCheck={false} className={field} />
                <button type="button" disabled={dirTest.isPending || dirty.length > 0} onClick={() => dirTest.mutate(dirUser.trim())} className={`${btnGhost} shrink-0`}>
                  {dirTest.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plug className="h-4 w-4" />}
                  Bağlan
                </button>
              </div>
              {dirTest.data && <div className="mt-2"><Note tone={dirTest.data.ok ? 'ok' : 'err'}>{dirTest.data.message}</Note></div>}
              {dirTest.error && <div className="mt-2"><Note tone="err">{errText(dirTest.error, 'Deneme yapılamadı.')}</Note></div>}
            </div>
          )}
          {GROUP_CHECK[g.id] && (() => {
            const gc = GROUP_CHECK[g.id];
            const busy = checking === gc.id;
            const r = result[gc.id];
            return (
              <div className="mt-2 rounded-xl bg-slate-50 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-[12.5px] font-bold">Bağlantı denemesi</div>
                    <p className="text-[11.5px] text-canvas-muted">{gc.help}</p>
                  </div>
                  <button type="button" disabled={busy} onClick={() => void saveAndCheck(gc.id)} className={`${btnPrimary} shrink-0`}>
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plug className="h-4 w-4" />}
                    {busy ? 'Sınanıyor…' : dirty.length ? 'Kaydet ve sına' : gc.label}
                  </button>
                </div>
                {r && !busy && <CheckResult r={r} />}
              </div>
            );
          })()}
        </Card>
      ))}

      {!searching && (current?.id === 'sistem' || cats.length <= 1) && system.data && (
        <Card>
          <div className="text-[14px] font-extrabold">Sistem tanımları</div>
          <p className="text-[12px] text-canvas-muted">
            Servisin açılışta okuduğu, ekrandan değiştirilmeyen tanımlar. Bir ayarın neden beklendiği gibi davranmadığı çoğu zaman burada yazar.
          </p>
          <dl className="mt-2 divide-y divide-slate-100">
            {system.data.items.map((i) => (
              <div key={i.label} className="grid gap-0.5 py-2 sm:grid-cols-[220px_1fr] sm:gap-4">
                <dt className="text-[12.5px] font-bold">{i.label}</dt>
                <dd className="min-w-0 break-all font-mono text-[11.5px] text-canvas-muted">{i.value || '—'}</dd>
              </div>
            ))}
          </dl>
        </Card>
      )}

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
            `${dirty.length} değişiklik kaydedilmedi${dirtyCats.length ? ` (${dirtyCats.join(', ')})` : ''}`
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
