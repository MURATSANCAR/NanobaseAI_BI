/** Known BI Postgres sources (ERP + Sigorta). Hosts/secrets stay in configs/ — not bundled. */

export type BiKnownSourceId = 'erp' | 'sigorta';

export type BiKnownSourceMeta = {
  id: BiKnownSourceId;
  label: string;
  /** Operator docs — see configs/sources/connection.example.json */
  seedFile: string;
  catalogFile: string;
  vaultSecretRef: string;
};

/** Default dual-source set used by Nanobase BI demos. */
export const BI_KNOWN_SOURCES: BiKnownSourceMeta[] = [
  {
    id: 'erp',
    label: 'ERP (Neon)',
    seedFile: 'configs/seeds/neon-erp-seed.sql',
    catalogFile: 'configs/schemas/erp.catalog.json',
    vaultSecretRef: 'bi/default/erp/password',
  },
  {
    id: 'sigorta',
    label: 'Sigorta (Neon)',
    seedFile: 'configs/seeds/neon-sigorta-seed.sql',
    catalogFile: 'configs/schemas/sigorta.catalog.json',
    vaultSecretRef: 'bi/default/sigorta/password',
  },
];

export function isKnownBiSourceId(id: string): id is BiKnownSourceId {
  return id === 'erp' || id === 'sigorta';
}
