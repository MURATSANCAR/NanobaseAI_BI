import type { CSSProperties, FormEvent, ReactNode } from 'react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

export const controlStyle: CSSProperties = {
	width: '100%', minWidth: 0, minHeight: 44, padding: 10, boxSizing: 'border-box',
	border: '1px solid #86919c', borderRadius: 6, color: '#1f2937', background: '#fff', fontSize: 16,
};

export const Field = ({ label, children }: { label: string; children: ReactNode }) => (
	<label style={{ display: 'grid', gap: 6, minWidth: 0 }}>{label}{children}</label>
);

export const SetupForm = ({ title, currentStep, stepCount, onSubmit, onBackButtonClick, children }: {
	title: string; currentStep: number; stepCount: number; children: ReactNode;
	onSubmit: (data: FormData) => Promise<void>;
	onBackButtonClick?: () => void;
}) => {
	const { t } = useTranslation('translation');
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState('');
	const submit = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (busy) return;
		const data = new FormData(event.currentTarget);
		setBusy(true);
		setError('');
		try { await onSubmit(data); } catch (error) {
			setError(error instanceof Error ? error.message : t('Error'));
		} finally { setBusy(false); }
	};
	return <main style={{ width: '100%', minHeight: '100dvh', padding: 16, boxSizing: 'border-box', background: '#f4f6f8', color: '#1f2937' }}>
		<form onSubmit={submit} style={{ width: '100%', maxWidth: 480, margin: '32px auto', display: 'grid', gap: 18, minWidth: 0 }}>
			<strong>ZEKI AI CHAT</strong>
			<h1 style={{ fontSize: 24, overflowWrap: 'anywhere' }}>{title}</h1>
			<p>{currentStep} / {stepCount}</p>
			<fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0, minWidth: 0, display: 'grid', gap: 16 }}>{children}</fieldset>
			{error && <p role='alert' style={{ color: '#b42318', overflowWrap: 'anywhere' }}>{error}</p>}
			<div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
				{onBackButtonClick && <button type='button' disabled={busy} onClick={onBackButtonClick} style={{ ...controlStyle, width: 'auto' }}>{t('Back')}</button>}
				<button type='submit' disabled={busy} style={{ ...controlStyle, width: 'auto', flex: 1, background: '#155eef', color: '#fff' }}>{t('Continue')}</button>
			</div>
		</form>
	</main>;
};
