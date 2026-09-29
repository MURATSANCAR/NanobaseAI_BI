import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Plus, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import { POSITION_TONE, fmtDay, hrApi, recruitApi, type Position, type RecruitMeta, type Warning } from '../hrApi';
import SqlInfo from '../../components/SqlInfo';
import { AskSheet, Block, HrFrame, splitUsers } from '../parts';
import { Explain } from '../../components/Explain';

/** M55 pozisyonlar: pozisyon kartı (birim, yetkinlikler, işe alan yönetici, görüşmeciler), Zeki AI ilan taslağı ve
 *  ayrımcılık denetimi, mülakat soru seti, onay akışı (İK açar, onaycı onaylar; gönderen onaylayamaz). */

export default function PositionEditor() {
  const [params, setParams] = useSearchParams();
  const selected = params.get('id') ?? '';
  const [state, setState] = useState('');
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['hr', 'recruit', 'meta'], queryFn: recruitApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const list = useQuery({ queryKey: ['hr', 'recruit', 'positions', state], queryFn: () => recruitApi.positions(state), enabled: ENGINE_ENABLED });
  const select = (id: string) => {
    const p = new URLSearchParams(params);
    if (id) p.set('id', id);
    else p.delete('id');
    setParams(p, { replace: true });
  };
  const create = useMutation({
    mutationFn: () => recruitApi.createPosition({ title: 'Yeni pozisyon' }),
    onSuccess: (p) => {
      void qc.invalidateQueries({ queryKey: ['hr', 'recruit'] });
      select(p.id);
    },
    onError: (e) => toast.error(errText(e, 'Pozisyon açılamadı.')),
  });
  const items = list.data?.items ?? [];
  const current = items.find((p) => p.id === selected);
  return (
    <HrFrame
      crumb="Pozisyonlar"
      title="Pozisyonlar"
      lead="Açılacak her kadronun kartı: birim, yetkinlikler, işe alan yönetici ve görüşmeciler. İlan metni ve mülakat soruları yetkinliklerden hazırlanır. İK kartı onaya gönderir; onaycı başvuruya açar ya da gerekçeyle geri gönderir."
      aside={
        meta.data?.me.can.positionOpen ? (
          <div className="flex justify-start lg:justify-end">
            <button type="button" className={btnPrimary} disabled={create.isPending} onClick={() => create.mutate()}>
              <Plus aria-hidden className="h-4 w-4" />
              Yeni pozisyon
            </button>
          </div>
        ) : undefined
      }
    >
      {list.error && <Note tone="err">{errText(list.error, 'Pozisyonlar okunamadı.')}</Note>}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)] lg:gap-4">
        <Block title="Pozisyonlar" info={
          <Explain label="Pozisyon durumları">
            <span className="block"><b>Taslak:</b> İK hazırlıyor.</span>
            <span className="block"><b>Onayda:</b> onaycının kararını bekliyor.</span>
            <span className="block"><b>Açık:</b> onaylandı, başvuru alıyor.</span>
            <span className="block"><b>Beklemede:</b> geçici olarak durduruldu.</span>
            <span className="block"><b>Kapandı:</b> alım bitti; kart artık değiştirilemez.</span>
          </Explain>
        } action={
          <select className={`${field} !min-h-9 !py-1`} value={state} onChange={(e) => setState(e.target.value)} aria-label="Durum">
            <option value="">Bütün durumlar</option>
            {Object.entries(meta.data?.positionStates ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        }>
          {list.isLoading && <div className="py-6 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
          {list.data && !items.length && (
            <div className="py-6 text-center text-[12px] text-canvas-muted">
              {state ? 'Bu durumda pozisyon yok; durum süzgecini «Bütün durumlar» yapın.' : 'Henüz pozisyon açılmadı.'}
            </div>
          )}
          {!!items.length && (
            <div className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold text-canvas-muted">
              Aday sayıları <SqlInfo k={list.data?.kaynaklar} alan="items[]" label="Pozisyon başına aday sayısı" />
            </div>
          )}
          <ul className="flex flex-col gap-1.5">
            {items.map((p) => {
              const n = Object.values(p.counts).reduce((a, b) => a + (b ?? 0), 0);
              return (
                <li key={p.id}>
                  <button
                    type="button"
                    onClick={() => select(p.id)}
                    aria-current={p.id === selected}
                    className={`w-full rounded-xl border p-2.5 text-left transition-colors duration-150 ${p.id === selected ? 'border-canvas-violet bg-canvas-violet/5' : 'border-slate-100 bg-white/80 hover:border-canvas-violet/40'}`}
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="min-w-0 break-words text-[13px] font-extrabold">{p.title}</span>
                      <Pill tone={POSITION_TONE[p.state]}>{p.stateLabel}</Pill>
                    </div>
                    <div className="text-[11.5px] text-canvas-muted">{p.unitName || 'Birim yok'} · {n} aday · {fmtDay(p.createdAt)}</div>
                  </button>
                </li>
              );
            })}
          </ul>
        </Block>
        {current && meta.data ? (
          <Editor key={current.id + current.updatedAt} p={current} meta={meta.data} />
        ) : (
          <Block title="Pozisyon kartı">
            <div className="py-8 text-center text-[12.5px] text-canvas-muted">Soldan bir pozisyon seçin{meta.data?.me.can.positionOpen ? ' ya da yeni pozisyon açın' : ''}.</div>
          </Block>
        )}
      </div>
    </HrFrame>
  );
}

function Editor({ p, meta }: { p: Position; meta: RecruitMeta }) {
  const qc = useQueryClient();
  const can = meta.me.can;
  const editable = can.positionOpen && !['onayda', 'kapandi'].includes(p.state);
  const units = useQuery({ queryKey: ['hr', 'units'], queryFn: hrApi.units, enabled: ENGINE_ENABLED, staleTime: 5 * 60_000 });
  const [f, setF] = useState({
    title: p.title, unitId: p.unitId ?? '', hiringManager: p.hiringManager ?? '', team: p.team.join(', '),
    competencies: p.competencies.join('\n'), note: p.note, postingText: p.postingText,
  });
  const [warnings, setWarnings] = useState<Warning[]>(p.postingWarnings);
  const [ask, setAsk] = useState<null | 'reject'>(null);
  const refresh = () => void qc.invalidateQueries({ queryKey: ['hr', 'recruit'] });
  const dirty = f.title !== p.title || f.unitId !== (p.unitId ?? '') || f.hiringManager !== (p.hiringManager ?? '') ||
    f.team !== p.team.join(', ') || f.competencies !== p.competencies.join('\n') || f.note !== p.note || f.postingText !== p.postingText;

  const save = useMutation({
    mutationFn: () => recruitApi.updatePosition(p.id, {
      title: f.title, unitId: f.unitId || null, hiringManager: f.hiringManager.trim().toLowerCase(), team: splitUsers(f.team),
      competencies: f.competencies.split('\n').map((x) => x.trim()).filter(Boolean), note: f.note, postingText: f.postingText,
    }),
    onSuccess: () => {
      toast.success('Pozisyon kaydedildi.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  const action = useMutation({
    mutationFn: (x: { a: 'submit' | 'withdraw' | 'approve' | 'reject' | 'hold' | 'resume' | 'close'; note?: string }) =>
      recruitApi.positionAction(p.id, x.a, x.note ?? ''),
    onSuccess: (r) => {
      toast.success(`Pozisyon: ${r.stateLabel}.`);
      setAsk(null);
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.')),
  });
  const draft = useMutation({
    mutationFn: () => recruitApi.postingDraft(p.id),
    onSuccess: (r) => {
      setF((x) => ({ ...x, postingText: r.text }));
      setWarnings(r.warnings);
      toast.success(r.warnings.length ? 'Taslak hazır; uyarıları gözden geçirin.' : 'Taslak hazır; okuyup kaydedin.');
    },
    onError: (e) => toast.error(errText(e, 'İlan taslağı yazılamadı.')),
  });
  const check = useMutation({
    mutationFn: () => recruitApi.postingCheck(p.id, f.postingText),
    onSuccess: (r) => {
      setWarnings(r.warnings);
      toast.success(r.warnings.length ? `${r.warnings.length} uyarı var.` : 'Ayrımcı koşul görülmedi.');
    },
    onError: (e) => toast.error(errText(e, 'Denetlenemedi.')),
  });
  const kit = useMutation({
    mutationFn: () => recruitApi.interviewKit(p.id),
    onSuccess: () => {
      toast.success('Mülakat soru seti hazır.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Soru seti hazırlanamadı.')),
  });

  return (
    <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
      <Block
        title="Pozisyon kartı"
        help={p.state === 'onayda' ? `Onayda · gönderen ${p.submittedBy ?? '—'}, ${fmtDay(p.submittedAt)}` : p.approvedBy ? `Onaylayan ${p.approvedBy}, ${fmtDay(p.approvedAt)}` : undefined}
        action={
          <>
            <Pill tone={POSITION_TONE[p.state]}>{p.stateLabel}</Pill>
            <Link to={`/ik/ise-alim?pozisyon=${p.id}`} className={btnGhost}>Adayları gör</Link>
          </>
        }
      >
        {p.reviewNote && p.state === 'taslak' && <Note tone="warn">Geri gönderme notu: {p.reviewNote}</Note>}
        <fieldset disabled={!editable} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={labelCls}>Pozisyon adı</span>
            <input className={field} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Birim</span>
            <select className={field} value={f.unitId} onChange={(e) => setF({ ...f, unitId: e.target.value })}>
              <option value="">Seçilmedi</option>
              {(units.data?.items ?? []).filter((u) => u.active || u.id === f.unitId).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>İşe alan yönetici (hesap adı)</span>
            <input className={field} value={f.hiringManager} onChange={(e) => setF({ ...f, hiringManager: e.target.value })} autoComplete="off" placeholder="ör. ayse.yilmaz" />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={labelCls}>Görüşmeciler (hesap adları, virgülle)</span>
            <input className={field} value={f.team} onChange={(e) => setF({ ...f, team: e.target.value })} autoComplete="off" placeholder="ör. mehmet.kaya, zeynep.demir" />
            <span className="text-[11px] text-canvas-muted">İşe alan yönetici ve görüşmeciler yalnız bu pozisyonun adaylarını görür (rollerinde «Adayları görme» varsa).</span>
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={labelCls}>Yetkinlikler (her satıra bir tane)</span>
            <textarea className={`${field} min-h-[120px]`} value={f.competencies} onChange={(e) => setF({ ...f, competencies: e.target.value })}
              placeholder={'Çocuk kitaplarında redaksiyon deneyimi\nİleri düzey İngilizce\nYayın takvimi yönetimi'} />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={labelCls}>Not (ilan taslağına girer)</span>
            <textarea className={`${field} min-h-[64px]`} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="ör. Hibrit çalışma, haftada iki gün ofis" />
          </label>
        </fieldset>
        <div className="mt-3 flex flex-wrap justify-end gap-2">
          {editable && (
            <button type="button" className={btnPrimary} disabled={!dirty || save.isPending} onClick={() => save.mutate()}>Kaydet</button>
          )}
          {can.positionOpen && p.state === 'taslak' && (
            <button type="button" className={btnGhost} disabled={dirty || action.isPending} onClick={() => action.mutate({ a: 'submit' })}>Onaya gönder</button>
          )}
          {can.positionOpen && p.state === 'onayda' && (
            <button type="button" className={btnGhost} disabled={action.isPending} onClick={() => action.mutate({ a: 'withdraw' })}>Geri çek</button>
          )}
          {can.positionApprove && p.state === 'onayda' && (
            <>
              <button type="button" className={btnGhost} disabled={action.isPending} onClick={() => setAsk('reject')}>Geri gönder</button>
              <button type="button" className={btnPrimary} disabled={action.isPending} onClick={() => action.mutate({ a: 'approve' })}>Onayla ve aç</button>
            </>
          )}
          {can.positionOpen && p.state === 'acik' && (
            <button type="button" className={btnGhost} disabled={action.isPending} onClick={() => action.mutate({ a: 'hold' })}>Beklemeye al</button>
          )}
          {can.positionOpen && p.state === 'beklemede' && (
            <button type="button" className={btnGhost} disabled={action.isPending} onClick={() => action.mutate({ a: 'resume' })}>Yeniden aç</button>
          )}
          {can.positionOpen && p.state !== 'kapandi' && (
            <button type="button" className={btnGhost} disabled={action.isPending} onClick={() => action.mutate({ a: 'close' })}>Pozisyonu kapat</button>
          )}
        </div>
      </Block>

      <Block
        title="İlan metni"
        help="Zeki AI yetkinliklerden taslak yazar; metni siz düzeltip kaydedersiniz. Ayrımcı koşul (yaş, cinsiyet, medeni hal, askerlik, görünüş…) kural ve Zeki AI ile denetlenir."
        action={
          editable ? (
            <>
              <button type="button" className={btnGhost} disabled={check.isPending || !f.postingText.trim()} onClick={() => check.mutate()}>
                {check.isPending ? 'Denetleniyor…' : 'Ayrımcı koşulu denetle'}
              </button>
              <button type="button" className={btnPrimary} disabled={draft.isPending || !meta.modelVar || !p.competencies.length} onClick={() => draft.mutate()}>
                {draft.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                Zeki AI taslağı
              </button>
            </>
          ) : undefined
        }
      >
        {editable && !p.competencies.length && <Note tone="info">Taslak için önce yetkinlikleri yazıp kaydedin.</Note>}
        {warnings.length > 0 && (
          <ul className="mb-2 flex flex-col gap-1">
            {warnings.map((w, i) => (
              <li key={i} className="rounded-lg bg-amber-50 px-2 py-1.5 text-[12.5px] leading-snug text-amber-900">
                <span className="font-bold">{w.label}</span>
                {w.text && <span> — «{w.text}»</span>}
                <span className="ml-1 text-[11px] text-amber-800/80">({w.source === 'zeki' ? 'Zeki AI' : 'kural'})</span>
              </li>
            ))}
          </ul>
        )}
        <textarea
          className={`${field} min-h-[220px] font-sans`}
          value={f.postingText}
          readOnly={!editable}
          onChange={(e) => setF({ ...f, postingText: e.target.value })}
          aria-label="İlan metni"
        />
        {editable && f.postingText !== p.postingText && (
          <div className="mt-2 flex justify-end">
            <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>İlanı kaydet</button>
          </div>
        )}
      </Block>

      <Block
        title="Mülakat soru seti"
        help="Yetkinlik başına davranışsal sorular ve iyi cevabın ölçütü. Yaş, aile, sağlık, din, askerlik konusunda soru önerilmez."
        action={
          (can.positionOpen || can.decide) && meta.modelVar ? (
            <button type="button" className={btnGhost} disabled={kit.isPending || !p.competencies.length} onClick={() => kit.mutate()}>
              {kit.isPending ? 'Hazırlanıyor…' : p.interviewKit.length ? 'Yeniden öner' : 'Zeki AI önersin'}
            </button>
          ) : undefined
        }
      >
        {!p.interviewKit.length && <div className="py-3 text-center text-[12px] text-canvas-muted">Henüz soru seti yok. Yetkinlikler kaydedildikten sonra Zeki AI’a önerdirebilirsiniz.</div>}
        <ul className="flex flex-col gap-2">
          {p.interviewKit.map((k) => (
            <li key={k.competency} className="rounded-xl border border-slate-100 bg-white/80 p-2.5">
              <div className="text-[13px] font-extrabold">{k.competency}</div>
              <ul className="ml-4 mt-1 list-disc text-[12.5px] leading-snug">{k.questions.map((q) => <li key={q}>{q}</li>)}</ul>
              {k.criteria && <div className="mt-1 text-[11.5px] text-canvas-muted">Ölçüt: {k.criteria}</div>}
            </li>
          ))}
        </ul>
      </Block>
      <AskSheet
        open={ask === 'reject'}
        title="Pozisyonu geri gönder"
        message="Pozisyon taslağa döner; gönderen notunuzu görür."
        confirm="Geri gönder"
        input="Gerekçe"
        required
        busy={action.isPending}
        onClose={() => setAsk(null)}
        onConfirm={(note) => action.mutate({ a: 'reject', note })}
      />
    </div>
  );
}
