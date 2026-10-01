import type { PlaywrightTestConfig } from '@playwright/test';

import * as constants from './tests/e2e/config/constants';

export default {
	globalSetup: require.resolve('./tests/e2e/config/global-setup.ts'),
	use: {
		channel: 'chromium',
		headless: true,
		ignoreHTTPSErrors: true,
		trace: 'retain-on-failure',
		baseURL: constants.BASE_URL,
		screenshot: process.env.CI ? 'off' : 'only-on-failure',
		video: process.env.CI ? 'off' : 'retain-on-failure',
		launchOptions: {
			// force GPU hardware acceleration
			// (even in headless mode)
			args: ['--use-gl=egl', '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
		},
		permissions: ['microphone'],
	},
	outputDir: 'tests/e2e/.playwright',
	reporter: [['list']],

	testDir: 'tests/e2e',
	testIgnore: 'tests/e2e/federation/**',
	workers: 1,
	timeout: 60 * 1000,
	globalTimeout: (process.env.IS_EE === 'true' ? 50 : 40) * 60 * 1000,
	maxFailures: process.env.CI ? 5 : undefined,
	// Retry on CI only.
	retries: parseInt(String(process.env.PLAYWRIGHT_RETRIES)) || 0,
} as PlaywrightTestConfig;
