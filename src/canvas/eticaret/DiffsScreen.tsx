import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, FileSpreadsheet, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel, Pager, useDebounced } from '../editorial/kit';
import { ecomApi, isEan, type Diff, type DiffKind, type Meta } from './api';
import { DiffCard, EticaretFrame, MarkSheet } from './parts';
import SqlInfo from '../components/SqlInfo';
import { EmptyHint, Explain } from '../components/Explain';
import ItemDrawer from './ItemDrawer';
import { xlsxUrl } from '../components/excel';

/** M34 Farklar (eşitleme raporu): her satır bir kitabın bir farkı; CRM, Logo ve site değerleri yan yana. Süzgeçler adres
 *  çubuğunda (?tur=, ?durum=, ?q=, ?sahip=). Seçilen farklar topluca işaretlenir; barkodlu kitapların içerik paketi indirilir. */
export default function DiffsScreen() {
  const meta = useQuery({ queryKey: ['eticaret', 'meta'], queryFn: ecomApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  return (
    <EticaretFrame
      title="Farklar"
      lead="Sitedeki ürün ile CRM kartı ve Logo kaydı arasındaki her uyumsuzluk bir satırdır; «D&R fiyat farkı» TİMAŞ kitabının D&R'de sitemizden ucuz ya da farklı liste fiyatıyla satıldığını gösterir. Farkı T-soft'ta ya da CRM'de düzeltip «Düzeltildi» diye işaretleyin; ertesi gece doğrulanır. Bilerek bıraktığınız fark (ör. kampanya fiyatı) değerler değişmedikçe yeniden açılmaz."
      source="Kaynak: site kaydı · CRM · Logo (kesim tarihiyle) · D&R kataloğu (son görüntü)"
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu ekranın veri bağlantısı kurulmamış; liste açılamaz. Lütfen sistem yöneticinize bildirin.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Ekran bilgisi okunamadı.')}</Note>}
      {meta.data && <Listing meta={meta.data} />}
    </EticaretFrame>
  );
}

function Listing({ meta }: { meta: Meta }) {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tur = params.get('tur') ?? '';
  const durum = params.get('durum') ?? '';
  const sahip = params.get('sahip') ?? '';
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q, 300);
  const [page, setPage] = useState(0);
  const [picked, setPicked] = useState<Record<string, Diff>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [marking, setMarking] = useState<Diff[] | null>(null);

  const update = useCallback((next: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    setParams(p, { replace: true });
    setPage(0);
    setPicked({});
  }, [params, setParams]);

  const filter = { tur, durum, q: dq, sahip };
  const list = useQuery({
    queryKey: ['eticaret', 'diffs', tur, durum, dq, sahip, page],
    queryFn: () => ecomApi.diffs({ ...filter, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: (prev) => prev,
  });
  const items = list.data?.items ?? [];
  const pickedList = useMemo(() => Object.values(picked), [picked]);
  const packKeys = useMemo(() => [...new Set(pickedList.map((d) => d.productKey).filter(isEan))], [pickedList]);

  const markBulk = useMutation({
    mutationFn: (b: { ids: string[]; durum: Exclude<Diff['durum'], 'kapandi'>; note: string; sahip: string | null }) =>
      b.ids.length === 1 ? ecomApi.mark(b.ids[0], { durum: b.durum, note: b.note, sahip: b.sahip }).then((d) => ({ items: [d], atlanan: [] as Array<{ id: string; neden: string }> })) : ecomApi.markBulk(b),
    onSuccess: (r) => {
      setMarking(null);
      setPicked({});
      qc.invalidateQueries({ queryKey: ['eticaret'] });
      toast.success(`${r.items.length} fark işaretlendi.${r.atlanan.length ? ` ${r.atlanan.length} tanesi atlandı (kapanmış).` : ''}`);
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });

  const kinds = Object.keys(meta.turler) as DiffKind[];
  const counts = list.data?.turSayilari;
  return (
    <>
      <Panel>
        <div className="-mx-1 overflow-x-auto px-1">
          <div className="flex w-max gap-1.5">
            <Chip on={!tur} onClick={() => update({ tur: null })}>Hepsi{counts ? ` · ${Object.values(counts).reduce((a, b) => a + b, 0)}` : ''}</Chip>
            {kinds.map((k) => (
              <Chip key={k} on={tur === k} onClick={() => update({ tur: k })}>
                {meta.turler[k]}{counts ? ` · ${counts[k]}` : ''}
              </Chip>
            ))}
            {counts && <span className="flex items-center"><SqlInfo k={list.data?.kaynaklar} alan="turSayilari" label="Türe göre fark sayıları" /></span>}
          </div>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr]">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ara</span>
            <span className="relative flex items-center">
              <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
              <input className={`${field} pl-9`} value={q} placeholder="Kitap adı, barkod, stok kodu"
                onChange={(e) => { setQ(e.target.value); update({ q: e.target.value || null }); }} />
            </span>
          </label>
          <div className="flex flex-col gap-1">
            <span className={`${labelCls} inline-flex items-center gap-1`}>
              <label htmlFor="eticaret-fark-durum">Durum</label>
              <Explain label="Fark durumları">Açık: henüz ele alınmadı. Düzeltildi: siz düzelttiniz, gece okumasında doğrulanacak. Bilerek bırakıldı: fark kasıtlı, değerler değişmedikçe açılmaz. Sonraya: belirli bir süre listeden kalkar. Kapandı: fark ortadan kalktı.</Explain>
            </span>
            <select id="eticaret-fark-durum" className={field} value={durum} onChange={(e) => update({ durum: e.target.value || null })}>
              <option value="">İş bekleyenler (açık + sonra)</option>
              <option value="acik-hepsi">Kapanmamış olanların hepsi</option>
              {Object.entries(meta.durumlar).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              <option value="hepsi">Hepsi (kapananlar dahil)</option>
            </select>
          </div>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Sorumlu kişi</span>
            <input className={field} defaultValue={sahip} placeholder="Kullanıcı adı (boş: herkes)" autoComplete="off"
              onBlur={(e) => update({ sahip: e.target.value.trim() || null })}
              onKeyDown={(e) => { if (e.key === 'Enter') update({ sahip: (e.target as HTMLInputElement).value.trim() || null }); }} />
          </label>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {meta.me.canMark && (
            <button type="button" className={btnPrimary} disabled={!pickedList.length} onClick={() => setMarking(pickedList)}>
              Seçilenleri işaretle{pickedList.length ? ` (${pickedList.length})` : ''}
            </button>
          )}
          {meta.me.canExport && (
            <>
              <a className={`${btnGhost} ${packKeys.length ? '' : 'pointer-events-none opacity-50'}`} aria-disabled={!packKeys.length}
                href={packKeys.length ? ecomApi.contentPackUrl(packKeys) : undefined}>
                <FileSpreadsheet aria-hidden className="h-4 w-4" />
                İçerik paketini indir{packKeys.length ? ` (${packKeys.length} kitap)` : ''}
              </a>
              <a className={btnGhost} href={ecomApi.diffsCsvUrl({ tur, durum, q: dq, sahip })}>
                <Download aria-hidden className="h-4 w-4" />
                Listeyi indir (CSV)
              </a>
              <a className={btnGhost} href={xlsxUrl(ecomApi.diffsCsvUrl({ tur, durum, q: dq, sahip }))}>
                <FileSpreadsheet aria-hidden className="h-4 w-4" />
                Listeyi indir (Excel)
              </a>
            </>
          )}
          {(meta.me.canMark || meta.me.canExport) && items.length > 0 && (
            <button type="button" className={btnGhost}
              onClick={() => setPicked((p) => (items.every((d) => p[d.id]) ? {} : { ...p, ...Object.fromEntries(items.map((d) => [d.id, d])) }))}>
              {items.every((d) => picked[d.id]) ? 'Seçimi kaldır' : 'Bu sayfayı seç'}
            </button>
          )}
          {meta.me.canExport && (
            <Explain label="İçerik paketi">Seçtiğiniz barkodlu kitapların kart bilgilerini (Excel) indirir; sitedeki ürün sayfasını düzeltirken kullanılır. Barkodu olmayan kayıtlar pakete girmez.</Explain>
          )}
        </div>
      </Panel>
      <Panel>
        {list.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
        {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
        {list.data && !items.length && <EmptyHint title="Bu süzgece uyan fark yok" why="Fark türünü «Hepsi»ne alın, durumu değiştirin ya da aramayı temizleyin." />}
        <div className="flex flex-col gap-2">
          {items.map((d) => (
            <DiffCard key={d.id} d={d} onOpen={setOpen} k={list.data?.kaynaklar}
              selected={!!picked[d.id]}
              onSelect={meta.me.canMark || meta.me.canExport ? (on) => setPicked((p) => {
                const n = { ...p };
                if (on) n[d.id] = d;
                else delete n[d.id];
                return n;
              }) : undefined}
              onMark={meta.me.canMark ? (x) => setMarking([x]) : undefined} />
          ))}
        </div>
        {list.data && (
          <div className="flex items-start gap-1">
            <div className="min-w-0 flex-1">
              <Pager page={page} pageSize={list.data.pageSize} total={list.data.total} shown={items.length}
                loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
            </div>
            <SqlInfo k={list.data.kaynaklar} alan="total" label="Fark sayısı (süzgece uyan)" className="mt-2" />
          </div>
        )}
      </Panel>
      {marking && (
        <MarkSheet key={marking.map((d) => d.id).join(',')} open meta={meta} count={marking.length}
          initial={marking.length === 1 ? { durum: marking[0].durum === 'kapandi' ? undefined : marking[0].durum, sahip: marking[0].sahip } : undefined}
          busy={markBulk.isPending} onClose={() => setMarking(null)}
          onSave={(b) => markBulk.mutate({ ids: marking.map((d) => d.id), ...b })} />
      )}
      <ItemDrawer itemKey={open} meta={meta} onClose={() => setOpen(null)} />
    </>
  );
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick}
      className={`inline-flex min-h-11 shrink-0 items-center whitespace-nowrap rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
        on ? 'bg-canvas-violet text-white shadow-md' : 'bg-white/70 text-canvas-ink hover:bg-white'
      }`}>
      {children}
    </button>
  );
}
