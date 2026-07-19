export type ApiErrorDetail = {
  field?: string;
  code?: string;
  message: string;
};

export class ApiError extends Error {
  readonly code: string;
  readonly traceId: string;
  readonly status: number;
  readonly details: ApiErrorDetail[];

  constructor(opts: {
    code: string;
    message: string;
    traceId?: string;
    status?: number;
    details?: ApiErrorDetail[];
  }) {
    super(opts.message);
    this.name = 'ApiError';
    this.code = opts.code;
    this.traceId = opts.traceId || '';
    this.status = opts.status ?? 500;
    this.details = opts.details || [];
  }

  static async fromResponse(response: Response): Promise<ApiError> {
    const status = response.status;
    let body: Record<string, unknown> = {};
    try {
      body = (await response.json()) as Record<string, unknown>;
    } catch {
      const text = await response.text().catch(() => '');
      return new ApiError({
        code: status === 401 ? 'UNAUTHORIZED' : 'INTERNAL_ERROR',
        message: text || `HTTP ${status}`,
        status,
      });
    }
    return new ApiError({
      code: String(body.code || (status === 403 ? 'FORBIDDEN' : 'INTERNAL_ERROR')),
      message: String(body.message || body.error || `HTTP ${status}`),
      traceId: String(body.traceId || body.trace_id || ''),
      status,
      details: Array.isArray(body.details) ? (body.details as ApiErrorDetail[]) : [],
    });
  }

  /** User-facing message without driver secrets. */
  userMessage(): string {
    const map: Record<string, string> = {
      DATASOURCE_NOT_FOUND: 'Veritabanı bağlantısı bulunamadı.',
      DATASOURCE_CONNECTION_FAILED: 'Veritabanına bağlantı kurulamadı.',
      SCHEMA_SCAN_FAILED: 'Şema taraması tamamlanamadı.',
      SCHEMA_SCAN_ALREADY_RUNNING: 'Bu kaynak için bir tarama zaten çalışıyor.',
      TEXT_TO_SQL_ENGINE_UNAVAILABLE: 'SQL planlama servisine erişilemiyor.',
      TEXT_TO_SQL_PLAN_FAILED: 'Soru için SQL planı oluşturulamadı.',
      EXECUTION_DISABLED: 'Bu ortamda sorgu çalıştırma kapalıdır.',
      TENANT_ACCESS_DENIED: 'Bu kaynağa erişim yetkiniz bulunmuyor.',
      UNAUTHORIZED: 'Oturum gerekli veya süresi dolmuş.',
      FORBIDDEN: 'Bu işlem için yetkiniz yok.',
      VALIDATION_ERROR: 'Gönderilen bilgiler geçersiz.',
    };
    const base = map[this.code] || this.message || 'Beklenmeyen bir hata oluştu.';
    return this.traceId ? `${base} Destek kodu: ${this.traceId}` : base;
  }
}
