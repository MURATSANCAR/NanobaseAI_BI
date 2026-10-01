import type { ISchedulerModify } from './ISchedulerModify';
import type { IServerSettingsModify } from './IServerSettingsModify';
import type { ISlashCommandsModify } from './ISlashCommandsModify';

/**
 * This accessor provides methods for modifying the configuration
 * of ZEKI AI CHAT. It is provided during "onEnable" of your App.
 */
export interface IConfigurationModify {
	/** Accessor for modifying the settings inside of ZEKI AI CHAT. */
	readonly serverSettings: IServerSettingsModify;

	/** Accessor for modifying the slash commands inside of ZEKI AI CHAT. */
	readonly slashCommands: ISlashCommandsModify;

	/** Accessor for modifying schedulers */
	readonly scheduler: ISchedulerModify;
}
