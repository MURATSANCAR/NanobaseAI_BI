import type { ISetting } from '@zeki.chat/core-typings';
import { Settings } from '@zeki.chat/models';

export async function findIntegrationSettings(): Promise<{ settings: ISetting[] }> {
	const settings = await Settings.findByIds([
		'Livechat_webhookUrl',
		'Livechat_secret_token',
		'Livechat_http_timeout',
		'Livechat_webhook_on_start',
		'Livechat_webhook_on_close',
		'Livechat_webhook_on_chat_taken',
		'Livechat_webhook_on_chat_queued',
		'Livechat_webhook_on_forward',
		'Livechat_webhook_on_offline_msg',
		'Livechat_webhook_on_visitor_message',
		'Livechat_webhook_on_agent_message',
	]).toArray();

	return { settings };
}
