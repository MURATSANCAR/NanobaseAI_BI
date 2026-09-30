import type { Reporter, TestCase, TestResult } from '@playwright/test/reporter';
import fetch from 'node-fetch';

class ZekiChatReporter implements Reporter {
	private url: string;

	private apiKey: string;

	private branch: string;

	private draft: boolean;

	private run: number;

	constructor(options: { url: string; apiKey: string; branch: string; draft: boolean; run: number }) {
		this.url = options.url;
		this.apiKey = options.apiKey;
		this.branch = options.branch;
		this.draft = options.draft;
		this.run = options.run;
	}

	async onTestEnd(test: TestCase, result: TestResult) {
		if (process.env.REPORTER_ZEKICHAT_REPORT !== 'true') {
			console.log('REPORTER_ZEKICHAT_REPORT is not true, skipping', {
				draft: this.draft,
				branch: this.branch,
			});
			return;
		}
		const payload = {
			name: test.title,
			status: result.status,
			duration: result.duration,
			branch: this.branch,
			draft: this.draft,
			run: this.run,
		};

		try {
			const res = await fetch(this.url, {
				method: 'POST',
				body: JSON.stringify(payload),
				headers: {
					'Content-Type': 'application/json',
					'X-Api-Key': this.apiKey,
				},
			});

			if (!res.ok) {
				console.error('Error sending test result to ZEKI AI CHAT', JSON.stringify(payload), res);
			}
		} catch (error) {
			console.error('Unknown error while sending test result to ZEKI AI CHAT', JSON.stringify(payload), error);
		}
	}
}

export default ZekiChatReporter;
