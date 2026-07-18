import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, Palette, Upload } from 'lucide-react';
import ApiErrorBanner from '@/components/ApiErrorBanner';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { apiBase } from '@/api/http';
import type { BiBrandingSettings } from '@/api/types';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';

const DEFAULTS: BiBrandingSettings = {
  brand_name: 'NanobaseAI',
  logo_url: '',
  primary_color: '#7c3aed',
  accent_color: '#2563eb',
  footer_text: '',
  allowed_tables: [],
};

function resolveLogoSrc(base: string, url?: string): string | undefined {
  if (!url) return undefined;
  if (/^https?:\/\//i.test(url) || url.startsWith('data:')) return url;
  const root = base.replace(/\/$/, '');
  return url.startsWith('/') ? `${root}${url}` : `${root}/${url}`;
}

export default function BiBrandingSettingsForm() {
  const { config } = useApiConfig();
  const qc = useQueryClient();
  const [form, setForm] = useState<BiBrandingSettings>(DEFAULTS);
  const [savedFlash, setSavedFlash] = useState(false);

  const settings = useQuery({
    queryKey: ['bi-settings', config],
    queryFn: () => api.bi.settings.get(config),
    enabled: isRunnerConfigured(config),
  });

  useEffect(() => {
    if (settings.data) {
      setForm({
        brand_name: settings.data.brand_name || DEFAULTS.brand_name,
        logo_url: settings.data.logo_url || '',
        primary_color: settings.data.primary_color || DEFAULTS.primary_color,
        accent_color: settings.data.accent_color || DEFAULTS.accent_color,
        footer_text: settings.data.footer_text || '',
        allowed_tables: settings.data.allowed_tables || [],
      });
    }
  }, [settings.data]);

  const saveMut = useMutation({
    mutationFn: () => api.bi.settings.save(config, form),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['bi-settings'] });
      setSavedFlash(true);
      window.setTimeout(() => setSavedFlash(false), 4000);
    },
  });

  const uploadMut = useMutation({
    mutationFn: (file: File) => api.bi.settings.uploadLogo(config, file),
    onSuccess: (data) => {
      setForm((prev) => ({ ...prev, logo_url: data.logo_url || prev.logo_url }));
      void qc.invalidateQueries({ queryKey: ['bi-settings'] });
      setSavedFlash(true);
      window.setTimeout(() => setSavedFlash(false), 4000);
    },
  });

  const setField = <K extends keyof BiBrandingSettings>(key: K, value: BiBrandingSettings[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const logoPreview = resolveLogoSrc(apiBase(config) || window.location.origin, form.logo_url);

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="card space-y-4 p-4 sm:p-6">
        <div className="flex items-center gap-2">
          <Palette className="h-5 w-5 text-violet-600" />
          <h3 className="text-sm font-semibold text-slate-900">{t('bi.brandingTitle')}</h3>
        </div>
        <p className="text-xs text-slate-500">{t('bi.brandingHint')}</p>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">{t('bi.brandName')}</label>
          <input
            className="input-field"
            value={form.brand_name}
            onChange={(e) => setField('brand_name', e.target.value)}
            placeholder="NanobaseAI"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">{t('bi.logoUrl')}</label>
          <input
            className="input-field"
            value={form.logo_url}
            onChange={(e) => setField('logo_url', e.target.value)}
            placeholder={t('bi.branding.logoUrlPlaceholder')}
          />
          <p className="mt-1 text-[11px] text-slate-500">{t('bi.logoUploadHint')}</p>
          <label className="btn-secondary mt-2 inline-flex cursor-pointer items-center gap-2">
            <Upload className="h-4 w-4" />
            {uploadMut.isPending ? t('common.loading') : t('bi.logoUpload')}
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp,image/svg+xml,.png,.jpg,.jpeg,.webp,.svg"
              className="hidden"
              disabled={!isRunnerConfigured(config) || uploadMut.isPending}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) uploadMut.mutate(file);
                e.target.value = '';
              }}
            />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">{t('bi.primaryColor')}</label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                className="h-10 w-12 cursor-pointer rounded border border-slate-200"
                value={form.primary_color || '#7c3aed'}
                onChange={(e) => setField('primary_color', e.target.value)}
              />
              <input
                className="input-field font-mono text-xs"
                value={form.primary_color}
                onChange={(e) => setField('primary_color', e.target.value)}
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">{t('bi.accentColor')}</label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                className="h-10 w-12 cursor-pointer rounded border border-slate-200"
                value={form.accent_color || '#2563eb'}
                onChange={(e) => setField('accent_color', e.target.value)}
              />
              <input
                className="input-field font-mono text-xs"
                value={form.accent_color}
                onChange={(e) => setField('accent_color', e.target.value)}
              />
            </div>
          </div>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">{t('bi.footerText')}</label>
          <input
            className="input-field"
            value={form.footer_text}
            onChange={(e) => setField('footer_text', e.target.value)}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">{t('bi.allowedTables')}</label>
          <textarea
            className="input-field min-h-[72px] font-mono text-xs"
            value={(form.allowed_tables || []).join('\n')}
            onChange={(e) =>
              setField(
                'allowed_tables',
                e.target.value
                  .split(/[\n,]+/)
                  .map((s) => s.trim())
                  .filter(Boolean),
              )
            }
            placeholder={t('bi.allowedTablesPlaceholder')}
          />
          <p className="mt-1 text-[11px] text-slate-500">{t('bi.allowedTablesHint')}</p>
        </div>

        <button
          type="button"
          className="btn-primary"
          disabled={!isRunnerConfigured(config) || saveMut.isPending}
          onClick={() => saveMut.mutate()}
        >
          {saveMut.isPending ? t('common.loading') : t('bi.saveBranding')}
        </button>
        {savedFlash && <p className="text-sm text-status-ok">{t('bi.brandingSaved')}</p>}
        {savedFlash && (
          <Link to="/bi/shares" className="inline-flex items-center gap-1 text-sm font-medium text-violet-700 hover:underline">
            <ExternalLink className="h-3.5 w-3.5" />
            {t('bi.brandingShareCta')}
          </Link>
        )}
        <ApiErrorBanner error={(saveMut.error || uploadMut.error) as Error} />
        {settings.isError && (
          <p className="text-sm text-status-fail">{localizeUserMessage((settings.error as Error)?.message)}</p>
        )}
      </div>

      <div className="card overflow-hidden p-0">
        <div className="border-b border-slate-100 bg-slate-50 px-4 py-2 text-xs font-medium text-slate-500">
          {t('bi.brandingPreview')}
        </div>
        <div
          className="space-y-4 p-6"
          style={{
            ['--bi-brand' as string]: form.primary_color || '#7c3aed',
            ['--bi-accent' as string]: form.accent_color || '#2563eb',
          }}
        >
          <div className="flex items-center gap-3">
            {logoPreview ? (
              <img src={logoPreview} alt="" className="h-10 max-w-[140px] object-contain" />
            ) : (
              <div
                className="flex h-10 w-10 items-center justify-center rounded-lg text-sm font-bold text-white"
                style={{ background: form.primary_color || '#7c3aed' }}
              >
                {(form.brand_name || 'N').slice(0, 1).toUpperCase()}
              </div>
            )}
            <div>
              <p className="text-base font-semibold text-slate-900">{form.brand_name || 'NanobaseAI'}</p>
              <p className="text-xs text-slate-500">{t('bi.brandingPreviewPublic')}</p>
            </div>
          </div>
          <div className="flex gap-2">
            <span
              className="h-8 w-8 rounded-full border border-white shadow"
              style={{ background: form.primary_color }}
              title={t('bi.primaryColor')}
            />
            <span
              className="h-8 w-8 rounded-full border border-white shadow"
              style={{ background: form.accent_color }}
              title={t('bi.accentColor')}
            />
          </div>
          <div
            className="rounded-lg px-4 py-3 text-sm text-white"
            style={{ background: `linear-gradient(135deg, ${form.primary_color}, ${form.accent_color})` }}
          >
            {t('bi.brandingPreviewSampleKpi')}
          </div>
          {form.footer_text && <p className="text-xs text-slate-500">{form.footer_text}</p>}
        </div>
      </div>
    </div>
  );
}
