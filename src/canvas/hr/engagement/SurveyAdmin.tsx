import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Printer } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import Sheet from '../../editorial/studio/reader/Sheet';
import { fmtDay, fmtDateTime } from '../hrApi';
import { HrFrame, Tabs } from '../parts';
import { InfoLabel } from '../../components/SqlInfo';
import { SURVEY_TONE, engApi, type EngMeta, type Survey, type Template } from './engApi';
import { EmptyHint } from '../../components/Explain';

/** M58 Anket yönetimi (İK): şablonlar (ikinci kişi onaylar), anket açma, gösterim eşiği (kendiliğinden konmaz, İK girer;
 *  yalnız yükseltilir), birim kırılımı (eşik şart), basılı kodlar, kapanış ve birim sonucunu paylaşma. */

type Tab = 'anket' | 'sablon';

export default function SurveyAdmin() {
  const meta = useQuery({ queryKey: ['hr', 'eng', 'meta'], queryFn: engApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const [tab, setTab] = useState<Tab>('anket');
  return (
    <HrFrame crumb="Anket yönetimi" title="Anket yönetimi"
      lead="Onaylanmış şablondan adsız çalışan anketi başlatın, basılı kod üretin, kapatın ve birim sonuçlarını yöneticilerle paylaşın. Gösterim eşiği bir gizlilik kuralıdır: en az kaç yanıt olmadan sonuç gösterilmeyeceğini siz girersiniz; eşik girilmeden hiçbir sonuç görünmez.">
      <Tabs tabs={[{ key: 'anket' as const, label: 'Anketler' }, { key: 'sablon' as const, label: 'Şablonlar' }]} value={tab} onChange={setTab} />
      {meta.data && tab === 'anket' && <Surveys meta={meta.data} />}
      {meta.data && tab === 'sablon' && <Templates meta={meta.data} />}
    </HrFrame>
  );
}

function Surveys({ meta }: { meta: EngMeta }) {
  const q = useQuery({ queryKey: ['hr', 'eng', 'surveys'], queryFn: engApi.surveys });
  const [edit, setEdit] = useState<Survey | 'new' | null>(null);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-start"><button type="button" className={btnPrimary} onClick={() => setEdit('new')}><Plus aria-hidden className="h-4 w-4" />Yeni anket</button></div>
      {q.error && <Note tone="err">{errText(q.error, 'Anketler okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {q.data && !q.data.items.length && (
        <EmptyHint title="Henüz anket yok" why="«Yeni anket» ile onaylanmış bir şablondan anket hazırlayın; açınca hedef kitleye davet gider." />
      )}
      <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {(q.data?.items ?? []).map((s) => (
          <li key={s.id}>
            <button type="button" onClick={() => setEdit(s)} className="glass-panel flex w-full flex-col gap-1 rounded-2xl p-3 text-left shadow-glass-float">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="min-w-0 flex-1 break-words text-[14px] font-extrabold">{s.title}</span>
                <Pill tone={SURVEY_TONE[s.state]}>{s.stateLabel}</Pill>
              </div>
              <div className="text-[11.5px] text-canvas-muted">{s.kindLabel} · {fmtDay(s.opensAt)} – {fmtDay(s.closesAt)} · {s.audienceNames?.length ? s.audienceNames.join(', ') : 'bütün çalışanlar'}</div>
              <div className="flex flex-wrap gap-1.5 text-[11.5px]">
                <Pill tone={s.minGroup ? 'ok' : 'warn'}>{s.minGroup ? `gösterim eşiği ${s.minGroup}` : 'gösterim eşiği girilmedi'}</Pill>
                {s.unitBreakdown && <Pill tone="violet">birim kırılımlı</Pill>}
                {s.resultsSharedAt && <Pill tone="ok">birim sonucu paylaşıldı</Pill>}
              </div>
            </button>
          </li>
        ))}
      </ul>
      {edit !== null && <SurveySheet s={edit === 'new' ? null : edit} meta={meta} onClose={() => setEdit(null)} />}
    </div>
  );
}

function SurveySheet({ s, meta, onClose }: { s: Survey | null; meta: EngMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const tpls = useQuery({ queryKey: ['hr', 'eng', 'templates'], queryFn: engApi.templates });
  const today = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState({
    templateId: s?.templateId ?? '', title: s?.title ?? '', opensAt: s?.opensAt ?? today, closesAt: s?.closesAt ?? '',
    minGroup: s?.minGroup ? String(s.minGroup) : '', unitBreakdown: s?.unitBreakdown ?? false, units: s?.audience.units ?? ([] as string[]),
  });
  const [codes, setCodes] = useState<string[] | null>(null);
  const [n, setN] = useState('');
  const refresh = () => void qc.invalidateQueries({ queryKey: ['hr', 'eng'] });
  const draft = !s || s.state === 'taslak';
  const save = useMutation({
    mutationFn: () => {
      if (!draft) {
        const b: Record<string, unknown> = {};
        if (f.closesAt !== s!.closesAt && s!.state !== 'kapandi') b.closesAt = f.closesAt;
        if (f.minGroup && Number(f.minGroup) !== s!.minGroup) b.minGroup = Number(f.minGroup);
        return engApi.updateSurvey(s!.id, b);
      }
      const b = { templateId: f.templateId, title: f.title, opensAt: f.opensAt, closesAt: f.closesAt, units: f.units,
        unitBreakdown: f.unitBreakdown, ...(f.minGroup ? { minGroup: Number(f.minGroup) } : {}) };
      return s ? engApi.updateSurvey(s.id, b) : engApi.createSurvey(b);
    },
    onSuccess: () => { toast.success('Anket kaydedildi.'); refresh(); onClose(); },
    onError: (e) => toast.error(errText(e, 'Anket kaydedilemedi.')),
  });
  const act = useMutation({
    mutationFn: (a: 'open' | 'close' | 'share') => (a === 'open' ? engApi.open(s!.id) : a === 'close' ? engApi.close(s!.id) : engApi.share(s!.id)),
    onSuccess: (x) => { toast.success(`${x.stateLabel}${x.state === 'acik' ? ` · ${x.invited} davet` : ''}`); refresh(); onClose(); },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.')),
  });
  const paper = useMutation({
    mutationFn: () => engApi.paperCodes(s!.id, Number(n)),
    onSuccess: (r) => { setCodes(r.codes); refresh(); },
    onError: (e) => toast.error(errText(e, 'Kod üretilemedi.')),
  });
  const approved = (tpls.data?.items ?? []).filter((t) => t.state === 'yururlukte');
  return (
    <Sheet open modal wide onClose={onClose} title={s ? s.title : 'Yeni anket'} subtitle={s ? `${s.kindLabel} · ${s.stateLabel}` : undefined}>
      <div className="flex flex-col gap-3">
        {draft && (
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Şablon (onaylanmış)</span>
            <select className={field} value={f.templateId} onChange={(e) => setF({ ...f, templateId: e.target.value })}>
              <option value="">Seçin</option>
              {approved.map((t) => <option key={t.id} value={t.id}>{t.title} · {t.kindLabel} (sürüm {t.version})</option>)}
            </select>
            {!approved.length && <span className="text-[11.5px] text-amber-800">Onaylanmış şablon yok; «Şablonlar» sekmesinden hazırlayıp ikinci bir kişiye onaylatın.</span>}
          </label>
        )}
        {draft && (
          <label className="flex flex-col gap-1"><span className={labelCls}>Başlık (boşsa şablon adı)</span><input className={field} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1"><span className={labelCls}>Açılış</span><input type="date" className={field} disabled={!draft} value={f.opensAt} onChange={(e) => setF({ ...f, opensAt: e.target.value })} /></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Kapanış</span><input type="date" className={field} disabled={s?.state === 'kapandi'} value={f.closesAt} onChange={(e) => setF({ ...f, closesAt: e.target.value })} /></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Gösterim eşiği</span>
            <input className={field} inputMode="numeric" value={f.minGroup} onChange={(e) => setF({ ...f, minGroup: e.target.value.replace(/\D/g, '') })} placeholder="ör. 5" />
          </label>
        </div>
        <p className="text-[11.5px] leading-snug text-canvas-muted">Eşik: en az bu kadar yanıt olmadan hiçbir kapsamda (şirket ya da birim) sonuç gösterilmez. Girildikten sonra yalnız yükseltilir. Boş bırakılırsa sonuç eşik girilene kadar görünmez.</p>
        {draft && (
          <>
            <label className="flex min-h-11 items-center gap-2 text-[12.5px] font-bold">
              <input type="checkbox" checked={f.unitBreakdown} disabled={!f.minGroup} onChange={(e) => setF({ ...f, unitBreakdown: e.target.checked })} />
              Sonuçları birim birim de göster (yalnız eşik girilmişse; anket açıldıktan sonra değişmez)
            </label>
            <fieldset className="flex flex-col gap-1">
              <span className={labelCls}>Hedef kitle (boş: bütün aktif çalışanlar)</span>
              <div className="flex max-h-44 flex-col gap-1 overflow-y-auto rounded-xl bg-slate-50 p-2">
                {meta.units.map((u) => (
                  <label key={u.id} className="flex min-h-9 items-center gap-2 text-[12.5px]">
                    <input type="checkbox" checked={f.units.includes(u.id)} onChange={(e) => setF({ ...f, units: e.target.checked ? [...f.units, u.id] : f.units.filter((x) => x !== u.id) })} />{u.name}
                  </label>
                ))}
              </div>
            </fieldset>
          </>
        )}
        {s && (s.state === 'acik' || s.state === 'planli') && (
          <div className="flex flex-col gap-2 rounded-2xl bg-slate-50 p-3">
            <div className="text-[13px] font-extrabold">Basılı kod (bilgisayarsız çalışanlar)</div>
            <div className="flex flex-wrap gap-2">
              <input className={`${field} w-28`} inputMode="numeric" value={n} onChange={(e) => setN(e.target.value.replace(/\D/g, ''))} placeholder="Adet" />
              <button type="button" className={btnGhost} disabled={paper.isPending || !n} onClick={() => paper.mutate()}>Kod üret</button>
              {codes && <button type="button" className={btnGhost} onClick={() => window.print()}><Printer aria-hidden className="h-4 w-4" />Yazdır</button>}
            </div>
            {codes && (
              <>
                <Note tone="warn">Kodlar yalnız şimdi görünür; sayfayı kapatmadan yazdırın. Kodlar kişiye bağlı değildir; karıştırarak dağıtın. Çalışan, portal adresinin sonuna /ik/anket/k yazıp kodunu girer.</Note>
                <ul className="grid grid-cols-2 gap-1 font-mono text-[13px] sm:grid-cols-4">{codes.map((c) => <li key={c} className="rounded-lg bg-white px-2 py-1 text-center">{c}</li>)}</ul>
              </>
            )}
          </div>
        )}
        {s && (s.state === 'acik' || s.state === 'planli') && (
          <p className="text-[11.5px] leading-snug text-canvas-muted">Anketi kapatınca yeni cevap alınmaz, kimin cevapladığı bilgisi silinir ve basılı kodlar geçersiz olur.</p>
        )}
        {s && <div className="text-[11.5px] text-canvas-muted">Açılış {fmtDateTime(s.openedAt)} · davet {s.invited} · basılı kod {s.paperIssued}{s.closedAt ? ` · kapanış ${fmtDateTime(s.closedAt)}` : ''}</div>}
        <div className="flex flex-wrap justify-end gap-2">
          {s?.state === 'taslak' && <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate('open')}>Anketi aç</button>}
          {(s?.state === 'acik' || s?.state === 'planli') && <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate('close')}>Anketi kapat</button>}
          {s?.state === 'kapandi' && s.unitBreakdown && !s.resultsSharedAt && <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate('share')}>Birim sonuçlarını yöneticilerle paylaş</button>}
          <button type="button" className={btnPrimary} disabled={save.isPending || (draft && (!f.templateId || !f.closesAt))} onClick={() => save.mutate()}>Kaydet</button>
        </div>
      </div>
    </Sheet>
  );
}

function Templates({ meta }: { meta: EngMeta }) {
  const q = useQuery({ queryKey: ['hr', 'eng', 'templates'], queryFn: engApi.templates });
  const [edit, setEdit] = useState<Template | 'new' | null>(null);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-start"><button type="button" className={btnPrimary} onClick={() => setEdit('new')}><Plus aria-hidden className="h-4 w-4" />Yeni şablon</button></div>
      {q.error && <Note tone="err">{errText(q.error, 'Şablonlar okunamadı.')}</Note>}
      {!!q.data?.items.length && <div className="text-[11px] font-semibold text-canvas-muted"><InfoLabel k={q.data.kaynaklar} alan="items[]" label="Şablon soru sayısı">Soru sayıları</InfoLabel></div>}
      <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {(q.data?.items ?? []).map((t) => (
          <li key={t.id}>
            <button type="button" onClick={() => setEdit(t)} className="glass-panel flex w-full flex-col gap-1 rounded-2xl p-3 text-left shadow-glass-float">
              <div className="flex flex-wrap items-center gap-1.5"><span className="min-w-0 flex-1 text-[14px] font-extrabold">{t.title}</span>
                <Pill tone={t.state === 'yururlukte' ? 'ok' : t.state === 'onayda' ? 'warn' : 'muted'}>{t.stateLabel}</Pill><span className="font-mono text-[11px]">sürüm {t.version}</span></div>
              <div className="text-[11.5px] text-canvas-muted">{t.kindLabel} · {t.questions.length} soru{t.approvedBy ? ` · onaylayan ${t.approvedBy}` : ''}</div>
            </button>
          </li>
        ))}
      </ul>
      {edit !== null && q.data && <TemplateSheet t={edit === 'new' ? null : edit} meta={meta} starters={q.data.starters} onClose={() => setEdit(null)} />}
    </div>
  );
}

function TemplateSheet({ t, meta, starters, onClose }: { t: Template | null; meta: EngMeta; starters: Record<string, { title: string; questions: unknown[] }>; onClose: () => void }) {
  const qc = useQueryClient();
  const [kind, setKind] = useState(t?.kind ?? 'baglilik');
  const [title, setTitle] = useState(t?.title ?? '');
  const [text, setText] = useState(t ? JSON.stringify(t.questions, null, 2) : '');
  const done = () => { void qc.invalidateQueries({ queryKey: ['hr', 'eng', 'templates'] }); onClose(); };
  const save = useMutation({
    mutationFn: () => {
      let questions: unknown;
      try { questions = JSON.parse(text); } catch { throw new Error('Soru metni bozuk; tırnak, virgül ve parantezleri kontrol edin.'); }
      const b = { kind, title, questions };
      return t ? engApi.updateTemplate(t.id, b) : engApi.createTemplate(b);
    },
    onSuccess: (x) => { toast.success(x.state === 'taslak' ? 'Kaydedildi; yürürlüğe girmesi için onaya gönderin.' : 'Kaydedildi.'); done(); },
    onError: (e) => toast.error(errText(e, 'Şablon kaydedilemedi.')),
  });
  const act = useMutation({
    mutationFn: (a: 'submit' | 'approve' | 'reject' | 'archive') => engApi.templateAction(t!.id, a),
    onSuccess: (x) => { toast.success(x.stateLabel); done(); },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.')),
  });
  const starter = starters[kind];
  return (
    <Sheet open modal wide onClose={onClose} title={t ? t.title : 'Yeni şablon'} subtitle="Sorular değişince sürüm artar ve şablon yeniden onay ister. Onaylayan, onaya gönderen kişi olamaz.">
      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1"><span className={labelCls}>Tür</span>
            <select className={field} value={kind} onChange={(e) => setKind(e.target.value)}>{Object.entries(meta.kinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          </label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Ad</span><input className={field} value={title} onChange={(e) => setTitle(e.target.value)} /></label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Sorular (örnek yapıyı koruyarak düzenleyin)</span>
          <span className="text-[11px] leading-snug text-canvas-muted">
            text = soru metni; type = enps (0–10 tavsiye), likert5 (1–5 katılım), secim (seçenekli) ya da acik (açık uçlu); options = seçenekler.
            Boşsa «Başlangıç sorularını yükle» ile hazır bir örnekten başlayın.
          </span>
          <textarea className={`${field} min-h-[300px] font-mono text-[12px]`} value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} />
        </label>
        {starter && !text.trim() && (
          <div className="flex justify-start"><button type="button" className={btnGhost} onClick={() => { setText(JSON.stringify(starter.questions, null, 2)); if (!title) setTitle(starter.title); }}>Başlangıç sorularını yükle</button></div>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          {t?.state === 'taslak' && <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate('submit')}>Onaya gönder</button>}
          {t?.state === 'onayda' && <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate('reject')}>Geri gönder</button>}
          {t?.state === 'onayda' && <button type="button" className={btnPrimary} disabled={act.isPending} onClick={() => act.mutate('approve')}>Onayla</button>}
          {t && t.state !== 'arsiv' && <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate('archive')}>Arşivle</button>}
          <button type="button" className={btnPrimary} disabled={save.isPending || !title.trim() || !text.trim()} onClick={() => save.mutate()}>Kaydet</button>
        </div>
      </div>
    </Sheet>
  );
}
