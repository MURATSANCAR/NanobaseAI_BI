import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, errText } from '../../admin/ui';
import { fmtDay } from '../hrApi';
import { Block, HrFrame } from '../parts';
import ResultView from './ResultView';
import { engApi } from './engApi';

/** M58 Birimimin sonucu: yöneticisi olduğum birimin, İK'nın paylaştığı anket sonuçları. Eşik altındaysa «üst birimle birlikte»
 *  notu çıkar; tek tek cevap, yorum ya da kimin katıldığı yoktur. */
export default function MyUnitResults() {
  const q = useQuery({ queryKey: ['hr', 'eng', 'my-units'], queryFn: engApi.myUnits, enabled: ENGINE_ENABLED });
  const d = q.data;
  return (
    <HrFrame crumb="Birimimin sonucu" title="Birimimin anket sonucu"
      lead="İK'nın paylaştığı anketlerde yöneticisi olduğunuz birimin toplu sonucu. Birimde yeterli yanıt yoksa sonuç üst birimle birlikte gösterilir; yorum metinleri size gelmez, temalar İK'dadır."
      aside={<div className="flex justify-start lg:justify-end"><Link className="text-[12.5px] font-bold text-canvas-violet hover:underline" to="/ik/aksiyonlar">Birimimin aksiyonları →</Link></div>}>
      {q.error && <Note tone="err">{errText(q.error, 'Sonuç okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {d && !d.units.length && <Note tone="info">Kayıtta yöneticisi olduğunuz bir birim yok.</Note>}
      {d && d.units.length > 0 && !d.results.length && <Note tone="info">Birim sonuçları henüz paylaşılmadı.</Note>}
      {d?.results.map((r, i) => (
        <Block key={`${r.survey.id}-${r.scope}-${i}`} title={`${r.survey.title} · ${r.unitName ?? ''}`} help={`Kapanış ${fmtDay(r.survey.closesAt)}`}>
          <ResultView r={r} k={d.kaynaklar} base="results[]" row={`${r.survey.id}:${r.scope}`} />
        </Block>
      ))}
    </HrFrame>
  );
}
