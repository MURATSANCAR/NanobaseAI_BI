
import { oembedCron } from '../cron/oembed';
import { startCron } from '../cron/start';
import { temporaryUploadCleanupCron } from '../cron/temporaryUploadsCleanup';
import { userDataDownloadsCron } from '../cron/userDataDownloads';
import { videoConferencesCron } from '../cron/videoConferences';


export const startCronJobs = async (): Promise<void> => {
	await Promise.all([startCron(), oembedCron(), temporaryUploadCleanupCron(), videoConferencesCron()]);
	userDataDownloadsCron();
};
