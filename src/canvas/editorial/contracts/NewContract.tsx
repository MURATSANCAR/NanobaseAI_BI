import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Note, btnGhost, btnPrimary, field } from '../../admin/ui';
import { ModuleFrame, Panel } from '../kit';
import { contractApi, metaOptions, type Terms } from './api';
import TermsForm from './TermsForm';
import DocumentExtract from './DocumentExtract';
import { extractApi, stillApplied, type Suggestion } from './extract';
import { Field, errMsg } from './ui';

/** Yeni sözleşme taslağı: şartlar + şablon. Kayıt «Taslak» açılır, numara TS-<yıl>-<sıra>. */

export const emptyTerms = (): Terms => ({
  title: '', kind: 'telif-alis', company: '', parties: [], books: [], paymentType: 'satis', basis: 'net', rates: {}, tiers: [],
  discountPct: null, currency: 'TRY', advance: null, advanceRecoupable: true, flatFee: null, withholdingPct: null,
  start: null, end: null, openEnded: false, years: null, periodMonths: 6, paymentDays: 30, printRun: null,
  territory: '', language: '', rights: {}, notes: '',
});

export default function NewContract() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const meta = useQuery(metaOptions());
  const tpls = useQuery({ queryKey: ['contracts', 'templates', 'sozlesme'], queryFn: () => contractApi.templates({ target: 'sozlesme' }) });
  const [terms, setTerms] = useState<Terms>(emptyTerms);
  const [tpl, setTpl] = useState<string>('auto');
  // Belgeden aktarılan şartlar: taslak açılınca hangilerinin formda kaldığı okumaya yazılır (kim neyi onayladı).
  const fromDoc = useRef<{ id: string; keys: string[]; s: Suggestion } | null>(null);
  const options = tpls.data?.items ?? [];
  const chosen = tpl === 'auto' ? options.find((t) => t.kind === terms.kind) ?? options.find((t) => !t.kind) : options.find((t) => t.id === tpl);
  const create = useMutation({
    mutationFn: () => contractApi.create(terms, chosen?.id),
    onSuccess: (r) => {
      toast.success(`${r.no} taslağı açıldı.`);
      const d = fromDoc.current;
      if (d) {
        extractApi.accepted(d.id, stillApplied(terms, d.s, d.keys), r.id).catch(() => toast.warning('Belgeden aktarılan alanların kaydı yazılamadı; taslak açıldı.'));
      }
      qc.invalidateQueries({ queryKey: ['contracts'] });
      nav(`/telif-sozlesme/${r.id}`);
    },
  });
  const m = meta.data;
  return (
    <ModuleFrame
      route="/telif-sozlesme"
      crumb="Sözleşmeler"
      title="Yeni sözleşme"
      lead="Yeni telif ya da lisans sözleşmesinin taslağını açın. Şartlar imzaya kadar serbestçe düzenlenir; sözleşme metni seçtiğiniz şablondan üretilir. Taslak portalda tutulur, CRM'e yazılmaz."
      source="Portal"
    >
      <div className="px-1">
        <Link to="/telif-sozlesme" className="inline-flex min-h-11 items-center gap-1 text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0">
          <ChevronLeft aria-hidden className="h-4 w-4" />
          Bütün sözleşmeler
        </Link>
      </div>
      {meta.error && <Note tone="err">{errMsg(meta.error)}</Note>}
      {m && !m.can.edit && <Note tone="warn">Sözleşme açma yetkiniz yok (Yönetim → Yetkiler → «Sözleşme düzenleme»).</Note>}
      {m && (
        <>
          <Panel>
            <Field
              label="Şablon"
              explain="Şablon, sözleşme metninin kalıbıdır; girdiğiniz şartlar (taraflar, oranlar, tarihler) metindeki yerlerine yerleşir. «Sözleşme türüne göre», aşağıda seçtiğiniz türün şablonunu kullanır."
              hint={chosen ? `${chosen.name} · sürüm ${chosen.version}${chosen.description ? ` — ${chosen.description}` : ''}` : 'Şablon seçilmezse metin sonra üretilir.'}>
              <select value={tpl} onChange={(e) => setTpl(e.target.value)} className={field}>
                <option value="auto">Sözleşme türüne göre</option>
                <option value="">Şablonsuz (metin sonra)</option>
                {options.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </Field>
          </Panel>
          <DocumentExtract
            meta={m}
            terms={terms}
            lock={!m.can.edit}
            onApply={(next, keys, id, sug) => {
              fromDoc.current = { id, keys, s: sug };
              setTerms(next);
            }}
          />
          <TermsForm value={terms} onChange={setTerms} meta={m} lock={!m.can.edit} />
          {create.error && <Note tone="err">{errMsg(create.error)}</Note>}
          {m.can.edit && !terms.title.trim() && <p className="px-1 text-[11.5px] text-canvas-muted">Taslağı açmak için sözleşme adını yazın.</p>}
          <div className="sticky bottom-0 z-10 -mx-1 flex flex-wrap justify-end gap-2 rounded-2xl bg-white/90 p-2 shadow-glass-float backdrop-blur">
            <Link to="/telif-sozlesme" className={btnGhost}>Vazgeç</Link>
            <button type="button" className={btnPrimary} disabled={!m.can.edit || !terms.title.trim() || create.isPending} onClick={() => create.mutate()}>
              {create.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
              Taslağı aç
            </button>
          </div>
        </>
      )}
    </ModuleFrame>
  );
}
