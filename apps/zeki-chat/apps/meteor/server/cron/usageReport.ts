import { AirGappedRestriction } from '@zeki.chat/capabilities';
import type { Logger } from '@rocket.chat/logger';
import { Statistics } from '@rocket.chat/models';

export const sendUsageReportAndComputeRestriction = async (statsToken?: string) => {
	// If the report failed to be sent we need to get the last existing token
	// to ensure that the restriction respects the warning period.
	// If no token is passed, the workspace will be instantly restricted.
	const token = statsToken || (await Statistics.findLastStatsToken());
	void AirGappedRestriction.computeRestriction(token);
};

export async function usageReportCron(logger: Logger): Promise<void> {
	// Zeki: usage report cron disabled. Nothing is sent to collector.rocket.chat.
	// computeRestriction is called once only to reset the stored
	// "remaining days" setting to -1 (no restriction).
	logger.info('Zeki: usage report cron disabled');
	void AirGappedRestriction.computeRestriction();
}
