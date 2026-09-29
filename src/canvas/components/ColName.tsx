import { readableName, useDisplayWordsVersion } from './readableName';

/**
 * Veriden gelen bir adı (kolon, alan, tablo) ekranda okunur yazar; ham ad üstüne gelince görünür.
 *
 *   <th><ColName name={c.name} /></th>        → «Net (12 ay)», title="net_12ay"
 *   <b><ColName name="LG_411_CLCARD" /></b>   → «Cari kart»
 *
 * Katalogdaki Türkçe yazım haritası gelince kendiliğinden yeniden çizilir. Yalnız görünüm: dosyaya/SQL'e giden ad değişmez.
 */
export default function ColName({ name, className }: { name: unknown; className?: string }) {
  useDisplayWordsVersion();
  const raw = name == null ? '' : String(name);
  const text = readableName(raw);
  return (
    <span className={className} title={text !== raw ? raw : undefined}>
      {text}
    </span>
  );
}
