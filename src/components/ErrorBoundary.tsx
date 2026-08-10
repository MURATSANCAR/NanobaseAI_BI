import { Component, type ErrorInfo, type ReactNode } from 'react';
import { RotateCcw } from 'lucide-react';
import { t } from '@/i18n';

type ErrorBoundaryProps = {
  children: ReactNode;
  /** Optional title shown above the retry button (defaults to common.error). */
  label?: string;
  /** Tighter padding for small seams (widget tiles, chart slots). */
  compact?: boolean;
  className?: string;
};

type ErrorBoundaryState = {
  error: Error | null;
};

/**
 * Generic render-error safety net: shows a compact fallback with a retry
 * button instead of blanking the whole app when a child crashes.
 */
export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface for diagnostics without breaking the UI.
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  private handleRetry = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    if (this.state.error) {
      const compact = this.props.compact;
      return (
        <div
          role="alert"
          className={[
            'flex flex-col items-center justify-center gap-2 rounded-xl border border-rose-200/80 bg-rose-50/70 text-center',
            compact ? 'p-3' : 'min-h-[10rem] p-6',
            this.props.className || '',
          ].join(' ')}
        >
          <p className={compact ? 'text-xs font-medium text-rose-900' : 'text-sm font-semibold text-rose-900'}>
            {this.props.label || t('common.error')}
          </p>
          <button
            type="button"
            className="inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-rose-300 bg-white px-2.5 py-1 text-xs font-medium text-rose-800 transition hover:bg-rose-100"
            onClick={this.handleRetry}
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden />
            {t('common.retry')}
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
