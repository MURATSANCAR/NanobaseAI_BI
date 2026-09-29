import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, btnGhost, errText, field, label, nf } from '../../admin/ui';
import { dateTime } from '../../format';
import { useCan } from '../../useAdmin';
import { Panel } from '../kit';
import { FileButton, LANGS, langName } from './parts';
import { translationIoApi, type MemoryFile, type MemoryPair } from './ioApi';
import SqlInfo from '../../components/SqlInfo';
import { kaynakOf } from '../../components/kaynakOf';
import { EmptyHint } from '../../components/Explain';

/** Çeviri belleği: işlerde çevrilmiş/onaylı segmentler ve dışarıdan (TMX) alınan bellek. Çevirmen ekranındaki
 *  benzer cümle önerisi ikisine birden bakar; dış bellekten gelen öneri «Dış bellek: <dosya>» diye görünür. */

function FileRow({ pair, f, canManage, onChanged }: { pair: MemoryPair; f: MemoryFile; canManage: boolean; onChanged: () => void }) {
  const del = useMutation({ mutationFn: () => translationIoApi.deleteTmx(pair.sourceLang, pair.targetLang, f.origin), onSuccess: onChanged });
  return (
    <li className="rounded-xl border border-slate-100 bg-white px-2.5 py-2 text-[12px]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="min-w-0 break-words font-semibold leading-snug">{f.origin}</span>
        <span className="flex items-center gap-1">
          <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{nf.format(f.count)} kayıt</span>
          {canManage && (
            <button
              type="button"
              aria-label={`${f.origin} kayıtlarını kaldır`}
              disabled={del.isPending}
              onClick={() => {
                if (window.confirm(`«${f.origin}» dosyasından alınan ${nf.format(f.count)} bellek kaydı kaldırılsın mı? Bu geri alınamaz.`)) del.mutate();
              }}
              className={`${btnGhost} min-h-9 px-2.5 text-rose-700`}
            >
              <Trash2 aria-hidden className="h-4 w-4" />
            </button>
          )}
        </span>
      </div>
      {f.lastAt && (
        <p className="mt-0.5 text-[11px] text-canvas-muted">
          {dateTime(f.lastAt)}
          {f.by ? ` · ${f.by}` : ''}
        </p>
      )}
      {del.error && (
        <div className="mt-1.5">
          <Note tone="err">{errText(del.error, 'Kaldırılamadı.')}</Note>
        </div>
      )}
    </li>
  );
}

export default function MemoryBank() {
  const qc = useQueryClient();
  const canManage = useCan('ceviri.yonet');
  const canExport = useCan('veri.disa-aktar');
  const [src, setSrc] = useState('en');
  const [tgt, setTgt] = useState('tr');
  const [external, setExternal] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const memory = useQuery({ queryKey: ['translation', 'memory'], queryFn: translationIoApi.memory, enabled: ENGINE_ENABLED });
  const changed = () => void qc.invalidateQueries({ queryKey: ['translation', 'memory'] });
  const pairs = memory.data?.pairs ?? [];
  const same = src === tgt;

  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)] lg:items-start lg:gap-4">
      <Panel>
        <h2 className="px-1 text-[13px] font-extrabold">Dil çifti</h2>
        <p className="mt-0.5 px-1 text-[11.5px] leading-snug text-canvas-muted">
          Çeviri belleği, daha önce çevrilmiş cümle çiftlerinin arşividir. Çevirmen yeni bir cümlede çalışırken benzer eski çeviriler çeviri masasında önerilir.
        </p>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <label className="block">
            <span className={label}>Kaynak</span>
            <select value={src} onChange={(e) => setSrc(e.target.value)} className={`${field} mt-1`}>
              {Object.entries(LANGS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className={label}>Hedef</span>
            <select value={tgt} onChange={(e) => setTgt(e.target.value)} className={`${field} mt-1`}>
              {Object.entries(LANGS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        </div>
        {same && (
          <div className="mt-2">
            <Note tone="warn">Kaynak ve hedef dil aynı olamaz.</Note>
          </div>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          <div className="w-full">
            <FileButton
              tone="hero"
              feature="ceviri.yonet"
              accept=".tmx,.xml"
              disabled={same}
              disabledReason="Kaynak ve hedef dil aynı olamaz; üstten dil çiftini düzeltin."
              hint="Seçili dil çiftinin birimleri çeviri belleğine eklenir; bellekte zaten olan birim atlanır."
              run={(f) => translationIoApi.importTmx(src, tgt, f)}
              onDone={(r) => {
                setNotice(
                  `TMX: ${nf.format(r.added)} çeviri birimi belleğe eklendi` +
                    (r.duplicates ? `, ${nf.format(r.duplicates)} birim bellekte zaten vardı` : '') +
                    (r.skipped ? `, ${nf.format(r.skipped)} birimde bu dil çifti yoktu` : '') +
                    '.',
                );
                changed();
              }}
            >
              TMX dosyası yükle (çeviri belleği)
            </FileButton>
          </div>
          {canExport && !same && (
            <a href={translationIoApi.tmxUrl(src, tgt, external)} className={btnGhost}>
              <Download aria-hidden className="h-4 w-4" />
              TMX indir
            </a>
          )}
        </div>
        {canExport && (
          <label className="mt-2 flex min-h-11 items-center gap-2 px-1 text-[12px] font-semibold sm:min-h-9">
            <input type="checkbox" checked={external} onChange={(e) => setExternal(e.target.checked)} />
            İndirilen dosyaya dışarıdan alınan bellek de girsin
          </label>
        )}
        <p className="mt-2 px-1 text-[11px] leading-snug text-canvas-muted">
          TMX, çeviri programlarının (Trados, memoQ, OmegaT, Phrase) bellek dosyası biçimidir. Bölgesel dil kodu (en-US, tr-TR) seçilen dile sayılır; bellekte zaten olan cümle çifti ikinci kez yazılmaz. İndirilen dosyada bu dil çiftindeki bütün
          işlerin çevrilmiş ve onaylı segmentleri vardır.
        </p>
        {notice && (
          <div className="mt-2">
            <Note tone="ok">{notice}</Note>
          </div>
        )}
      </Panel>

      <Panel>
        <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
          <h2 className="text-[13px] font-extrabold">Bellekteki dil çiftleri</h2>
          <span className="flex items-center gap-1 font-mono text-[11px] tabular-nums text-canvas-muted">
            {nf.format(pairs.length)}
            <SqlInfo k={kaynakOf(memory.data)} alan="_hepsi" label="Bellek kayıt sayıları" />
          </span>
        </div>
        {memory.error && <Note tone="err">{errText(memory.error, 'Çeviri belleği okunamadı.')}</Note>}
        {memory.isLoading ? (
          <Loading />
        ) : !pairs.length ? (
          <div className="mt-3">
            <EmptyHint
              title="Bellek henüz boş"
              why="Çeviri işlerinde çevrilen cümleler buraya kendiliğinden eklenir. Elinizde eski bir bellek dosyası (TMX) varsa soldan yükleyebilirsiniz."
            />
          </div>
        ) : (
          <ul className="mt-2 space-y-2">
            {pairs.map((p) => {
              const active = p.sourceLang === src && p.targetLang === tgt;
              return (
                <li key={`${p.sourceLang}-${p.targetLang}`} className={`rounded-2xl border p-3 ${active ? 'border-canvas-violet bg-white' : 'border-slate-100 bg-white/85'}`}>
                  <button
                    type="button"
                    className="flex w-full flex-wrap items-baseline justify-between gap-2 text-left"
                    aria-pressed={active}
                    onClick={() => {
                      setSrc(p.sourceLang);
                      setTgt(p.targetLang);
                    }}
                  >
                    <span className="text-[12.5px] font-extrabold">
                      {langName(p.sourceLang)} → {langName(p.targetLang)}
                    </span>
                    <span className="font-mono text-[11px] tabular-nums text-canvas-muted">
                      {nf.format(p.segments)} iş segmenti · {nf.format(p.external)} dış kayıt
                    </span>
                  </button>
                  {p.files.length > 0 && (
                    <ul className="mt-2 space-y-1.5">
                      {p.files.map((f) => (
                        <FileRow key={f.origin} pair={p} f={f} canManage={canManage} onChanged={changed} />
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
    </div>
  );
}
