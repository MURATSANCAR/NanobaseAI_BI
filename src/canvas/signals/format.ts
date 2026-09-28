import type { NoteLabel, Today, TodayItem, VoiceLabel } from './api';

/** Öneri 15/16/19 ekranlarının saf yardımcıları (vitest ile sınanır). */

/** Trendyol iadesinin okur sesi anahtarı: köprüde `talep_id:barkod`. */
export const claimKey = (talepId: string, barkod: string) => `${talepId}:${barkod}`;

/** Etiketin nasıl konduğu; «Zeki AI» yalnız modelin gerçekten seçtiği yerde. */
export function topicHow(label: Pick<VoiceLabel, 'yontem'>): string {
  if (label.yontem === 'zeki') return 'Zeki AI';
  if (label.yontem === 'emin-degil') return 'Zeki AI emin değil';
  return 'kurala göre';
}

/** Sayısı sıfırdan büyük sinyal etiketleri («yok» hariç), verilen sırayla. */
export function activeLabels(sayilar: Record<NoteLabel, number>): NoteLabel[] {
  return (Object.keys(sayilar) as NoteLabel[]).filter((k) => k !== 'yok' && (sayilar[k] ?? 0) > 0);
}

export const urgentCount = (items: TodayItem[] | undefined) => (items ?? []).filter((x) => x.oncelik === 1).length;

/** «Bugün» panelinde gösterilecek özet: güncel Zeki AI özeti varsa o, yoksa kural özeti. */
export function todayText(d: Pick<Today, 'ozet' | 'kuralOzeti'>): { text: string; byModel: boolean } {
  if (d.ozet && d.ozet.guncel && d.ozet.metin) return { text: d.ozet.metin, byModel: true };
  return { text: d.kuralOzeti, byModel: false };
}

/** Panel açılınca Zeki AI'dan özet istenmeli mi (bir kez; model var, madde var, özet yok ya da eski). */
export function shouldAskModel(d: Pick<Today, 'modelVar' | 'items' | 'ozet'>): boolean {
  return d.modelVar && d.items.length > 0 && !(d.ozet && d.ozet.guncel);
}
