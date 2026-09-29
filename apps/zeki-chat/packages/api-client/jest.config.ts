import client from '@zeki.chat/jest-presets/client';
import type { Config } from 'jest';

export default {
	preset: client.preset,
	setupFilesAfterEnv: [...client.setupFilesAfterEnv],
} satisfies Config;
