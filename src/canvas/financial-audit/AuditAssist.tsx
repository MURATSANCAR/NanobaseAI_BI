import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Layers, Loader2, Sparkles } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import SqlEvidence from './SqlEvidence';

/** Bulgu açıklaması ve istisna kümeleme. Bulgu kuraldır ve değişmez; Zeki AI yalnız açıklar (sayı denetimli) ve
 *  kuralın karar veremediği istisna gruplarına muhtemel sınıf önerir. «Zeki AI» etiketi yalnız model kullanıldığında. */

export type Explanation = { checkId: string; metin: string | null; kaynak?: 'zeki' | 'kural'; neden?: string | null; nedenler?: string[]; belgeler?: string[]; sql?: string | null };
export type ClusterGroup = { label: string; rows: number; amount: string; firstDate: string | null; lastDate: string | null; class: string | null; classLabel: string | null; source: 'kural' | 'zeki' | 'incele'; probability: number | null };
export type Clusters = {
  state: 'none' | 'running' | 'ready' | 'error'; message?: string; groups?: ClusterGroup[];
  summary?: Array<{ class: string; label: string; rows: number; groups: number; amount: string }>;
  totalRows?: number; sql?: string | null; model?: boolean; asOf?: string; asked?: number; failed?: number;
};

const number = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 });
const day = (s?: string | null) => (s ? new Date(s).toLocaleDateString('tr-TR') : '—');

async function send<T>(path: string, method: 'GET' | 'POST'): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda Logo bağlantısı tanımlı değil.');
  const r = await fetch(`${ENGINE_BASE}/api/v1/financial-audit/${path}`, { method, credentials: 'include', signal: AbortSignal.timeout(180000) });
  if (!r.ok) {
    if (r.status === 401) throw new Error('Oturum açmanız gerekiyor.');
    if (r.status === 403) throw new Error('Bu işlem rolünüzde yok.');
    const b = await r.json().catch(() => null);
    throw new Error(typeof b?.detail === 'string' ? b.detail : b?.detail?.message ?? 'İstek tamamlanamadı.');
  }
  return r.json();
}

/** «Bu bulgu ne demek?» — tıklanınca bir kez yazılır, rapor klasöründe saklanır. */
export function ExplainFinding({ runId, checkId }: { runId: string; checkId: string }) {
  const [data, setData] = useState<Explanation | null>(null);
  const ask = useMutation({
    mutationFn: () => send<Explanation>(`runs/${runId}/explain/${checkId}`, 'POST'),
    onSuccess: setData,
  });
  if (!data?.metin) {
    return (
      <div className="audit-assist">
        <button type="button" className="audit-button" disabled={ask.isPending} onClick={() => ask.mutate()}>
          {ask.isPending ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Sparkles size={15} aria-hidden />}
          {ask.isPending ? 'Açıklama yazılıyor…' : 'Bu bulgu ne demek?'}
        </button>
        {ask.error && <p role="alert">{ask.error instanceof Error ? ask.error.message : 'Açıklama alınamadı.'}</p>}
      </div>
    );
  }
  return (
    <div className="audit-assist" aria-live="polite">
      <b>{data.kaynak === 'zeki' ? 'Zeki AI açıklaması' : 'Kurala göre açıklama'}</b>
      <p>{data.metin}</p>
      <small>Bulgu kuraldan gelir ve değişmez; açıklama yalnız yorumdur.{data.kaynak !== 'zeki' && data.neden ? ' Model metni sayı denetiminden geçmediği ya da model yanıt vermediği için kural metni gösteriliyor.' : ''}</small>
    </div>
  );
}

/** İstisnaları nedene göre gruplar: grup ve tutar SQL'den, sınıf kuraldan; kuralın bilemediği gruba Zeki AI önerisi. */
export function ExceptionClusters({ runId, checkId }: { runId: string; checkId: string }) {
  const qc = useQueryClient();
  const key = ['audit-clusters', runId, checkId];
  const q = useQuery({
    queryKey: key,
    queryFn: () => send<Clusters>(`runs/${runId}/clusters/${checkId}`, 'GET'),
    refetchInterval: (s) => (s.state.data?.state === 'running' ? 2000 : false),
    retry: false,
  });
  const start = useMutation({
    mutationFn: () => send<Clusters>(`runs/${runId}/clusters/${checkId}`, 'POST'),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
  const d = q.data;
  const running = d?.state === 'running' || start.isPending;
  return (
    <div className="audit-assist audit-clusters">
      <div className="audit-section-head">
        <div><span className="audit-eyebrow">NEDENE GÖRE GRUPLAR</span><h3>İstisnalar hangi nedene benziyor?</h3></div>
        {d?.state !== 'ready' && (
          <button type="button" className="audit-button" disabled={running} onClick={() => start.mutate()}>
            {running ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Layers size={15} aria-hidden />}
            {running ? 'Gruplanıyor…' : 'Nedene göre grupla'}
          </button>
        )}
      </div>
      <p>Bütün istisnalar hesap, işlem türü ve aya göre gruplanır. Sınıf önce kuraldan gelir (karşı kayıt yok, tutar iki katı, ters işaret, tarih farkı); kuralın bilemediği gruplara Zeki AI muhtemel sınıf önerir, emin değilse «incelenecek» kalır. Sınıf hüküm değildir.</p>
      {(d?.state === 'error' || start.error) && <p role="alert">{d?.message ?? (start.error instanceof Error ? start.error.message : 'Gruplanamadı.')}</p>}
      {d?.state === 'ready' && d.groups && (
        <>
          <div className="audit-cluster-summary">
            {d.summary?.map((s) => (
              <article key={s.class} className={s.class === 'incele' ? 'unsure' : ''}>
                <span>{s.label}</span><strong>{number.format(s.rows)}</strong>
                <small>{s.groups} grup · {number.format(Number(s.amount))} ₺ (mutlak)</small>
              </article>
            ))}
          </div>
          <SqlEvidence sql={d.sql} description={`Grupları ve kural sınıfını hesaplayan, çalıştırılmış sorgudur (kesim ${day(d.asOf)}); ${number.format(d.totalRows ?? 0)} istisna satırı.`} title="Gruplamanın SQL sorgusu" />
          <div className="audit-table-scroll">
            <table>
              <thead><tr><th>Grup</th><th>Muhtemel sınıf</th><th>Kayıt</th><th>Tutar (mutlak)</th><th>Tarih aralığı</th></tr></thead>
              <tbody>
                {d.groups.map((g, i) => (
                  <tr key={i}>
                    <td>{g.label}</td>
                    <td>{g.source === 'incele' ? <span className="audit-badge unverified">İncelenecek{g.classLabel ? ` · belki ${g.classLabel}` : ''}</span>
                      : <span className="audit-badge">{g.classLabel} · {g.source === 'zeki' ? `Zeki AI${g.probability != null ? ` %${Math.round(g.probability * 100)}` : ''}` : 'kurala göre'}</span>}</td>
                    <td>{number.format(g.rows)}</td>
                    <td>{number.format(Number(g.amount))} ₺</td>
                    <td>{day(g.firstDate)} – {day(g.lastDate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!d.model && <p>Model bu kurulumda tanımlı değil; kuralın bilemediği gruplar «incelenecek» kaldı.</p>}
          {!!d.failed && <p>{d.failed} grup için model yanıt vermedi; bunlar «incelenecek».</p>}
        </>
      )}
    </div>
  );
}
