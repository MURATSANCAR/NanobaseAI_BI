import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ExternalLink, Loader2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { AskSheet } from '../budget/parts';
import { DROP_REASON, EVENT_LABEL, KIT_TONE, SOURCE_LABEL, TONE_TONE, fmtDay, fmtStamp, prApi, type Kit, type Meta, type Part } from './api';
import { Block, Empty, PrFrame, useJob } from './parts';
import KitSends from './KitSends';

/** PR dosyası: bülten (ulusal/yerel), kişiye özel e-posta şablonu, Zeki AI taslağı, onay, gönderim listesi, öneri,
 *  yansımalar, geçmiş. Onaylı dosyanın metni değişirse dosya taslağa döner (ekranda uyarılır). */

const TEXTS: Array<{ part: Exclude<Part, 'openings'>; key: 'releaseNational' | 'releaseLocal' | 'pitchTemplate'; label: string; help: string; rows: string }> = [
  { part: 'national', key: 'releaseNational', label: 'Basın bülteni (ulusal)', help: 'Onaya giden ana metin.', rows: 'min-h-[260px]' },
  { part: 'local', key: 'releaseLocal', label: 'Basın bülteni (yerel)', help: 'Yerel basın için kısa sürüm (isteğe bağlı).', rows: 'min-h-[140px]' },
  { part: 'pitch', key: 'pitchTemplate', label: 'Kişiye özel e-posta şablonu', help: '{ad} ve {mecra} listeye eklenen her kişinin bilgisiyle dolar.', rows: 'min-h-[140px]' },
];

type Ask = null | 'submit' | 'approve' | 'reject' | 'close' | 'withdraw';

export default function PrKit() {
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['pr', 'meta'], queryFn: prApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const kitQ = useQuery({ queryKey: ['pr', 'kit', id], queryFn: () => prApi.kit(id), enabled: ENGINE_ENABLED && !!id });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['pr', 'kit', id] });
    qc.invalidateQueries({ queryKey: ['pr', 'home'] });
  };
  const kit = kitQ.data;
  const m = meta.data;
  const [ask, setAsk] = useState<Ask>(null);

  const act = useMutation({
    mutationFn: async ({ what, note }: { what: Exclude<Ask, null> | 'reopen'; note?: string }) => {
      if (what === 'submit') return prApi.submit(id);
      if (what === 'approve') return prApi.approve(id, note);
      if (what === 'reject') return prApi.reject(id, note ?? '');
      if (what === 'close') return prApi.close(id);
      if (what === 'withdraw') return prApi.withdraw(id);
      return prApi.reopen(id);
    },
    onSuccess: (k) => {
      qc.setQueryData(['pr', 'kit', id], k);
      qc.invalidateQueries({ queryKey: ['pr', 'home'] });
      setAsk(null);
      toast.success(`Dosya: ${k.statusLabel}.`);
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });

  const draft = useMutation({
    mutationFn: () => prApi.draft(id),
    onSuccess: () => {
      toast.success('Zeki AI taslağı hazırlanıyor.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Taslak başlatılamadı.') ?? ''),
  });
  const job = useJob(kit?.job?.kind === 'draft' ? kit.job : null, refresh);

  const aside = kit && m ? <Actions kit={kit} meta={m} busy={act.isPending} onAsk={setAsk} onReopen={() => act.mutate({ what: 'reopen' })} /> : null;

  return (
    <PrFrame
      crumb="PR dosyası"
      title={kit ? kit.bookTitle : 'PR dosyası'}
      lead={kit ? `Bu kitabın basın bülteni, gazetecilere gidecek e-postalar ve çıkan haberler. Önce dosya onaylanır, sonra her e-postayı siz tek tek gönderirsiniz. ${[kit.id, kit.author, kit.publishDate && `yayın ${fmtDay(kit.publishDate)}`, `sahibi ${kit.owner ?? '—'}`].filter(Boolean).join(' · ')}` : undefined}
      source="Portal kaydı · CRM yalnız okunur"
      presence={kit ? `${kit.sends.length} kişi` : '…'}
      back={{ to: '/basin-iliskileri', label: 'Basın ilişkileri' }}
      aside={aside}
    >
      {kitQ.isLoading && <Loading />}
      {kitQ.error && <Note tone="err">{errText(kitQ.error, 'Dosya açılamadı.')}</Note>}
      {kit && m && (
        <>
          {kit.status === 'geri' && kit.rejectNote && <Note tone="err">Geri gönderildi: {kit.rejectNote}</Note>}
          {kit.status === 'onayli' && <Note tone="info">Dosya onaylı. Bülten ya da şablon değişirse dosya taslağa döner ve gönderilmemiş satırların onayı düşer.</Note>}
          <Block
            title="Bülten ve metinler"
            info={<SqlInfo k={kit.kaynaklar} alan="draft" label="Taslak ve denetimde düşen cümleler" />}
            help="Zeki AI yalnız CRM kitap kartındaki metinlere ve künyeye dayanır; kaynakta birebir geçmeyen alıntı, kaynaksız rakam ve kanıtsız üstünlük iddiası içeren cümle düşer. Yazdığınız metin ezilmez: taslak yanında öneri olarak durur."
            action={
              m.me.canEdit && kit.status !== 'kapali' && kit.status !== 'onayda' ? (
                <button type="button" className={btnPrimary} disabled={draft.isPending || job.running || !m.modelReady} onClick={() => draft.mutate()}>
                  {draft.isPending || job.running ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                  {job.running ? job.live?.step ?? 'Zeki AI yazıyor' : 'Zeki AI taslağı'}
                </button>
              ) : null
            }
          >
            {!m.modelReady && <Note tone="warn">Zeki AI şu an bağlı değil; metinleri elle yazın.</Note>}
            {kit.job?.status === 'hata' && <Note tone="err">Son Zeki AI işi yarıda kaldı: {kit.job.error}</Note>}
            <Texts kit={kit} meta={m} onSaved={(k) => qc.setQueryData(['pr', 'kit', id], k)} />
            {kit.draft.openings?.metin && (
              <div className="mt-3 rounded-2xl border border-dashed border-canvas-violet/40 bg-white/70 p-3">
                <div className={labelCls}>Zeki AI · açılış cümlesi seçenekleri</div>
                <ul className="mt-1 flex list-disc flex-col gap-1 pl-5 text-[12.5px] leading-snug">
                  {kit.draft.openings.metin.split('\n').filter(Boolean).map((l, i) => <li key={i}>{l}</li>)}
                </ul>
              </div>
            )}
          </Block>

          <KitSends kit={kit} meta={m} onChange={refresh} />

          <Block
            title="Yansımalar"
            info={<SqlInfo k={kit.kaynaklar} alan="coverage" label="Dosyanın yansımaları" />}
            help="Bu kitap için kayıtlı haberler. Kişi ve kitap eşleşen gönderim satırı kendiliğinden «haber çıktı» olur."
            action={m.me.canEdit ? <Link to={`/basin-iliskileri/yansimalar?ekle=1&kitap=${encodeURIComponent(kit.crmBookId)}`} className={btnGhost}>Yansıma ekle</Link> : null}
          >
            {kit.coverage.length === 0 && <Empty>Henüz yansıma yok. Kitapla ilgili çıkan haberi «Yansımalar» ekranından ekleyin; gönderim yaptığınız kişiyle eşleşirse o satır kendiliğinden «haber çıktı» olur.</Empty>}
            <ul className="flex flex-col divide-y divide-slate-100">
              {kit.coverage.map((c) => (
                <li key={c.id} className="flex flex-wrap items-start justify-between gap-2 py-2">
                  <div className="min-w-0">
                    <div className="break-words text-[13px] font-bold leading-snug">
                      {c.url ? (
                        <a href={c.url} target="_blank" rel="noreferrer" className="inline-flex items-start gap-1 hover:underline">
                          {c.title}
                          <ExternalLink aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-canvas-muted" />
                        </a>
                      ) : c.title}
                    </div>
                    <div className="text-[11.5px] text-canvas-muted">{[fmtDay(c.publishedAt), c.outlet, c.stateLabel].filter((x) => x && x !== '—').join(' · ')}</div>
                  </div>
                  {c.tone && <Pill tone={TONE_TONE[c.tone]}>{c.toneLabel}</Pill>}
                </li>
              ))}
            </ul>
          </Block>

          <History id={kit.id} />
        </>
      )}

      <AskSheet
        open={ask === 'submit'}
        title="Onaya gönder"
        message={<>Bülten ve gönderim listesi ({kit?.sends.filter((s) => s.status === 'hazir').length ?? 0} kişi) pazarlama müdürünün onayına gider. Onaydan önce hiçbir gazeteciye e-posta gönderilemez.</>}
        confirm="Onaya gönder"
        busy={act.isPending}
        onClose={() => setAsk(null)}
        onConfirm={() => act.mutate({ what: 'submit' })}
      />
      <AskSheet
        open={ask === 'approve'}
        title="Dosyayı onayla"
        message="Bülten ve listedeki bütün satırlar birlikte onaylanır. E-postalar yine tek tek, bir kişinin elinden gider."
        confirm="Onayla"
        input="Not (isteğe bağlı)"
        busy={act.isPending}
        onClose={() => setAsk(null)}
        onConfirm={(note) => act.mutate({ what: 'approve', note })}
      />
      <AskSheet
        open={ask === 'reject'}
        title="Geri gönder"
        message="Dosya düzeltilmek üzere sahibine döner."
        confirm="Geri gönder"
        danger
        input="Gerekçe"
        required
        busy={act.isPending}
        onClose={() => setAsk(null)}
        onConfirm={(note) => act.mutate({ what: 'reject', note })}
      />
      <AskSheet
        open={ask === 'withdraw'}
        title="Onaydan geri çek"
        message="Dosya taslağa döner; düzeltip yeniden gönderebilirsiniz."
        confirm="Geri çek"
        busy={act.isPending}
        onClose={() => setAsk(null)}
        onConfirm={() => act.mutate({ what: 'withdraw' })}
      />
      <AskSheet
        open={ask === 'close'}
        title="Dosyayı kapat"
        message="Kapalı dosya değiştirilemez; kayıtları ve yansımaları durur. Gerekirse yeniden açılır."
        confirm="Kapat"
        busy={act.isPending}
        onClose={() => setAsk(null)}
        onConfirm={() => act.mutate({ what: 'close' })}
      />
    </PrFrame>
  );
}

function Actions({ kit, meta, busy, onAsk, onReopen }: { kit: Kit; meta: Meta; busy: boolean; onAsk: (a: Ask) => void; onReopen: () => void }) {
  const me = meta.me;
  const submitter = (kit.submittedBy ?? '').toLowerCase() === me.username.toLowerCase();
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1.5 text-[11.5px]">
        <Pill tone={KIT_TONE[kit.status]}>{kit.statusLabel}</Pill>
        <span className="text-canvas-muted">sürüm {kit.version}</span>
        {kit.approvedBy && <span className="text-canvas-muted">· onay {kit.approvedBy} ({fmtStamp(kit.approvedAt)})</span>}
        {kit.status === 'onayda' && <span className="text-canvas-muted">· gönderen {kit.submittedBy}</span>}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {me.canEdit && (kit.status === 'taslak' || kit.status === 'geri') && (
          <button type="button" className={btnPrimary} disabled={busy || !kit.releaseNational} onClick={() => onAsk('submit')}>Onaya gönder</button>
        )}
        {me.canApprove && kit.status === 'onayda' && !submitter && (
          <>
            <button type="button" className={btnPrimary} disabled={busy} onClick={() => onAsk('approve')}>Onayla</button>
            <button type="button" className={btnGhost} disabled={busy} onClick={() => onAsk('reject')}>Geri gönder</button>
          </>
        )}
        {me.canEdit && kit.status === 'onayda' && (
          <button type="button" className={btnGhost} disabled={busy} onClick={() => onAsk('withdraw')}>Onaydan geri çek</button>
        )}
        {me.canEdit && kit.status !== 'kapali' && kit.status !== 'onayda' && (
          <button type="button" className={btnGhost} disabled={busy} onClick={() => onAsk('close')}>Dosyayı kapat</button>
        )}
        {me.canEdit && kit.status === 'kapali' && (
          <button type="button" className={btnGhost} disabled={busy} onClick={onReopen}>Yeniden aç</button>
        )}
      </div>
      {kit.status === 'onayda' && submitter && <p className="text-[11.5px] text-canvas-muted">Onaya siz gönderdiniz; başka bir yetkili onaylar.</p>}
    </div>
  );
}

function Texts({ kit, meta, onSaved }: { kit: Kit; meta: Meta; onSaved: (k: Kit) => void }) {
  const editable = meta.me.canEdit && kit.status !== 'kapali' && kit.status !== 'onayda';
  const initial = () => ({ releaseNational: kit.releaseNational ?? '', releaseLocal: kit.releaseLocal ?? '', pitchTemplate: kit.pitchTemplate ?? '' });
  const [vals, setVals] = useState(initial);
  const [sources, setSources] = useState<Record<string, string>>({});
  useEffect(() => {
    setVals(initial());
    setSources({});
  }, [kit.releaseNational, kit.releaseLocal, kit.pitchTemplate]); // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = TEXTS.filter((t) => vals[t.key] !== (kit[t.key] ?? ''));
  const save = useMutation({
    mutationFn: () =>
      prApi.updateKit(kit.id, Object.fromEntries(dirty.flatMap((t) => [[t.key, vals[t.key] || null], [`${t.key}Source`, sources[t.key] ?? 'kullanici']]))),
    onSuccess: (k) => {
      onSaved(k);
      toast.success(k.status === 'taslak' && kit.status === 'onayli' ? 'Kaydedildi; dosya taslağa döndü, yeniden onay gerekir.' : 'Kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });

  return (
    <div className="flex flex-col gap-3">
      {TEXTS.map((t) => {
        const d = kit.draft[t.part];
        const suggestion = d?.metin && d.metin !== vals[t.key] ? d.metin : null;
        return (
          <div key={t.key} className="flex flex-col gap-1">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <label htmlFor={`pr-${t.key}`} className={labelCls}>{t.label}</label>
              <span className="text-[11px] text-canvas-muted">
                {kit.sources[t.part] ? `Kaynak: ${SOURCE_LABEL(kit.sources[t.part])}` : t.help}
              </span>
            </div>
            {editable ? (
              <textarea id={`pr-${t.key}`} className={`${field} ${t.rows} leading-snug`} value={vals[t.key]} onChange={(e) => setVals({ ...vals, [t.key]: e.target.value })} />
            ) : (
              <p id={`pr-${t.key}`} className="whitespace-pre-line rounded-xl bg-white/70 p-3 text-[12.5px] leading-snug">{kit[t.key] || '—'}</p>
            )}
            {suggestion && editable && (
              <details className="rounded-2xl border border-dashed border-canvas-violet/40 bg-white/70 p-3">
                <summary className="inline-flex min-h-8 cursor-pointer items-center gap-1 text-[12px] font-extrabold text-canvas-violet">
                  <Sparkles aria-hidden className="h-3.5 w-3.5" /> Zeki AI önerisi
                </summary>
                <p className="mt-1 whitespace-pre-line text-[12.5px] leading-snug">{suggestion}</p>
                <button type="button" className={`${btnGhost} mt-2`} onClick={() => { setVals({ ...vals, [t.key]: suggestion }); setSources({ ...sources, [t.key]: 'zeki' }); }}>
                  Metne al
                </button>
              </details>
            )}
            {(d?.dusen?.length ?? 0) > 0 && (
              <details className="text-[11.5px]">
                <summary className="inline-flex min-h-8 cursor-pointer items-center font-bold text-amber-800">Denetimde düşen {d!.dusen!.length} cümle</summary>
                <ul className="mt-1 flex flex-col gap-1 text-canvas-muted">
                  {d!.dusen!.map((x, i) => <li key={i}><strong>{DROP_REASON[x.neden] ?? x.neden}:</strong> {x.cumle}</li>)}
                </ul>
              </details>
            )}
          </div>
        );
      })}
      {editable && (
        <div className="flex flex-wrap justify-end gap-2">
          {dirty.length > 0 && <button type="button" className={btnGhost} onClick={() => setVals(initial())}>Geri al</button>}
          <button type="button" className={btnPrimary} disabled={!dirty.length || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </div>
      )}
    </div>
  );
}

function History({ id }: { id: string }) {
  const [open, setOpen] = useState(false);
  const q = useQuery({ queryKey: ['pr', 'events', id], queryFn: () => prApi.events(id), enabled: ENGINE_ENABLED && open });
  return (
    <Block title="Geçmiş" help="Dosyadaki her değişiklik: kim, ne zaman, ne yaptı." info={q.data ? <SqlInfo k={q.data.kaynaklar} alan="items" label="Değişiklik kaydı" /> : undefined}>
      <details onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
        <summary className="inline-flex min-h-8 cursor-pointer items-center text-[12px] font-bold text-canvas-violet">Geçmişi göster</summary>
        {q.isLoading && <Loading />}
        <ul className="mt-1 flex flex-col divide-y divide-slate-100 text-[12px]">
          {q.data?.items.map((e, i) => (
            <li key={i} className="flex flex-wrap justify-between gap-2 py-1.5">
              <span><strong>{EVENT_LABEL[e.what] ?? e.what}</strong> · {e.who}</span>
              <span className="text-canvas-muted">{fmtStamp(e.at)}</span>
            </li>
          ))}
        </ul>
      </details>
    </Block>
  );
}
