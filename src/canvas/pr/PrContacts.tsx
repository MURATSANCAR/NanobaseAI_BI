import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, RefreshCw, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Pager, useDebounced } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { fmtDay, prApi, type Meta } from './api';
import { Block, Empty, PrFrame } from './parts';

/** Medya kişileri: CRM'deki basın kişileri (mecrası dolu ya da CRM haberlerinde haberi yapan/görüşülen) + portalda
 *  eklenenler. CRM'e yazılmaz; not, konu etiketi ve «haberdar olmak istemiyor» işareti portalda tutulur. */
export default function PrContacts() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q.trim(), 300);
  const tur = params.get('tur') ?? '';
  const etiket = params.get('etiket') ?? '';
  const kaynak = params.get('kaynak') ?? '';
  const izin = params.get('izin') ?? '';
  const [page, setPage] = useState(0);
  const [adding, setAdding] = useState(false);
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p, { replace: true });
    setPage(0);
  };
  const meta = useQuery({ queryKey: ['pr', 'meta'], queryFn: prApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const list = useQuery({
    queryKey: ['pr', 'contacts', dq, tur, etiket, kaynak, izin, page],
    queryFn: () => prApi.contacts({ q: dq, tur, etiket, kaynak, izin, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const refresh = useMutation({
    mutationFn: () => prApi.contacts({ q: dq, tur, etiket, kaynak, izin, page, yenile: true }),
    onSuccess: (d) => qc.setQueryData(['pr', 'contacts', dq, tur, etiket, kaynak, izin, page], d),
    onError: (e) => toast.error(errText(e, 'CRM okunamadı.') ?? ''),
  });
  const m = meta.data;
  const d = list.data;

  return (
    <PrFrame
      crumb="Medya kişileri"
      title="Medya kişileri"
      lead="Gazeteci, editör, köşe yazarı, podcast ve video kanalı. CRM'deki basın kişileri ve portalda eklenenler tek listede; kişinin geçmiş haberleri, gönderimleri ve son teması kartında."
      source="CRM + portal"
      presence={d ? `${d.all.toLocaleString('tr-TR')} kişi` : '…'}
      aside={m?.me.canEdit ? (
        <button type="button" className={`${btnPrimary} w-full`} onClick={() => setAdding(true)}>
          <Plus aria-hidden className="h-4 w-4" /> Yeni medya kişisi
        </button>
      ) : undefined}
    >
      <Note tone="info">Kişisel veri: ad, e-posta ve telefon yalnız basın ilişkisi için tutulur. «Haberdar olmak istemiyorum» diyen kişiyi işaretleyin; bir daha önerilmez ve ona e-posta gitmez.</Note>
      {d?.note && <Note tone="warn">{d.note}</Note>}
      <Block title="Liste">
        <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-[1fr_180px_180px_160px_160px_auto] lg:items-end">
          <label className="relative flex items-center">
            <span className="sr-only">Ara</span>
            <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
            <input className={`${field} pl-9`} value={q} placeholder="Ad, mecra, e-posta" onChange={(e) => { setQ(e.target.value); setPage(0); }} />
          </label>
          <Select label="Mecra türü" value={tur} onChange={(v) => set('tur', v)} options={m?.outletTypes ?? {}} />
          <Select label="Konu" value={etiket} onChange={(v) => set('etiket', v)} options={Object.fromEntries((d?.tags ?? []).map((t) => [t, t]))} />
          <Select label="Kaynak" value={kaynak} onChange={(v) => set('kaynak', v)} options={{ crm: 'CRM', portal: 'Portalda eklenen' }} />
          <Select label="İletişim izni" value={izin} onChange={(v) => set('izin', v)} options={{ var: 'Açık', yok: 'İstemiyor' }} />
          <button type="button" className={btnGhost} onClick={() => refresh.mutate()} disabled={refresh.isPending}>
            <RefreshCw aria-hidden className={`h-4 w-4 ${refresh.isPending ? 'animate-spin' : ''}`} />
            <span className="lg:sr-only">CRM'den yenile</span>
          </button>
        </div>
        {list.isLoading && <Loading />}
        {list.error && <Note tone="err">{errText(list.error, 'Liste açılamadı.')}</Note>}
        {d && d.items.length === 0 && <Empty>Bu süzgeçle kişi yok.</Empty>}
        <ul className="grid grid-cols-1 gap-2 md:grid-cols-2 2xl:grid-cols-3">
          {d?.items.map((c) => (
            <li key={c.key}>
              <Link to={`/basin-iliskileri/kisi/${encodeURIComponent(c.key)}`} className="flex h-full flex-col gap-1 rounded-2xl border border-slate-100 bg-white/85 p-3 transition-colors duration-150 hover:border-canvas-violet/40">
                <span className="flex items-start justify-between gap-2">
                  <span className="break-words text-[13.5px] font-extrabold">{c.name}</span>
                  <span className="flex shrink-0 gap-1">
                    {c.source === 'portal' && <Pill tone="violet">Portal</Pill>}
                    {c.doNotContact && <Pill tone="err">İstemiyor</Pill>}
                  </span>
                </span>
                <span className="text-[11.5px] text-canvas-muted">{[c.outlet, c.outletType && m?.outletTypes[c.outletType], c.role].filter(Boolean).join(' · ') || '—'}</span>
                {c.topics.length > 0 && <span className="text-[11.5px]">{c.topics.join(' · ')}</span>}
                <span className="mt-auto text-[11px] text-canvas-muted">
                  {(c.crm?.haberSayisi ?? 0)} arşiv haberi · {c.history?.sends ?? 0} gönderim · {c.history?.coverage ?? 0} yansıma
                  {c.history?.last ? ` · son temas ${fmtDay(c.history.last)}` : ''}
                </span>
              </Link>
            </li>
          ))}
        </ul>
        {d && d.total > 0 && <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />}
      </Block>
      {m && adding && <ContactForm meta={m} onClose={() => setAdding(false)} />}
    </PrFrame>
  );
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: Record<string, string> }) {
  return (
    <label className="flex flex-col gap-1">
      <span className={labelCls}>{label}</span>
      <select className={field} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Hepsi</option>
        {Object.entries(options).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
    </label>
  );
}

/** Yeni ya da düzenlenen medya kişisi (portal). CRM kişisinde ad/e-posta CRM'dendir; burada yazılan değer portal
 *  örtüsüdür, CRM'e gitmez. */
export function ContactForm({ meta, initial, contactKey, onClose }: {
  meta: Meta;
  initial?: Partial<Record<'name' | 'outlet' | 'outletType' | 'role' | 'email' | 'phone' | 'region' | 'note', string | null>> & { topics?: string[] };
  contactKey?: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [start] = useState(() => ({
    name: initial?.name ?? '', outlet: initial?.outlet ?? '', outletType: initial?.outletType ?? '', role: initial?.role ?? '',
    email: initial?.email ?? '', phone: initial?.phone ?? '', region: initial?.region ?? '', note: initial?.note ?? '',
    topics: (initial?.topics ?? []).join(', '),
  }));
  const [v, setV] = useState(start);
  const save = useMutation({
    mutationFn: () => {
      // Düzenlemede yalnız değişen alan gider: CRM kişisinin CRM'deki adı/e-postası portal örtüsüne kopyalanmaz.
      const changed = contactKey ? Object.fromEntries(Object.entries(v).filter(([k, val]) => val !== start[k as keyof typeof start])) : v;
      const body: Record<string, unknown> = { ...changed };
      if ('outletType' in body) body.outletType = v.outletType || null;
      if ('region' in body) body.region = v.region || null;
      return contactKey ? prApi.updateContact(contactKey, body) : prApi.createContact(body);
    },
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ['pr', 'contacts'] });
      qc.invalidateQueries({ queryKey: ['pr', 'contact', c.key] });
      toast.success('Kaydedildi.');
      onClose();
      if (!contactKey) nav(`/basin-iliskileri/kisi/${encodeURIComponent(c.key)}`);
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const input = (k: keyof typeof v, label: string, type = 'text') => (
    <label className="flex flex-col gap-1">
      <span className={labelCls}>{label}</span>
      <input className={field} type={type} value={v[k]} onChange={(e) => setV({ ...v, [k]: e.target.value })} />
    </label>
  );
  return (
    <Sheet open modal onClose={onClose} title={contactKey ? 'Kişiyi düzenle' : 'Yeni medya kişisi'}
      subtitle={contactKey?.startsWith('crm:') ? 'CRM kişisi: burada yazılan portalda tutulur, CRM değişmez.' : undefined}>
      <div className="flex flex-col gap-2">
        {input('name', 'Ad soyad')}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {input('outlet', 'Mecra (gazete, dergi, kanal…)')}
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Mecra türü</span>
            <select className={field} value={v.outletType} onChange={(e) => setV({ ...v, outletType: e.target.value })}>
              <option value="">—</option>
              {Object.entries(meta.outletTypes).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          {input('role', 'Görevi')}
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Bölge</span>
            <select className={field} value={v.region} onChange={(e) => setV({ ...v, region: e.target.value })}>
              <option value="">—</option>
              {Object.entries(meta.regions).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          {input('email', 'E-posta', 'email')}
          {input('phone', 'Telefon', 'tel')}
        </div>
        {input('topics', 'Konular (virgülle: çocuk, tarih, kişisel gelişim…)')}
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Not</span>
          <textarea className={`${field} min-h-[80px]`} value={v.note} onChange={(e) => setV({ ...v, note: e.target.value })} />
        </label>
        <div className="flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={save.isPending || (contactKey ? JSON.stringify(v) === JSON.stringify(start) : !v.name.trim())} onClick={() => save.mutate()}>Kaydet</button>
        </div>
      </div>
    </Sheet>
  );
}
