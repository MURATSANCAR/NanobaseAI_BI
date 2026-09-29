import { LivechatPriorityWeight } from '@zeki.chat/core-typings';
import type { IRoom, ISubscription } from '@zeki.chat/core-typings';
import { mockAppRoot } from '@zeki.chat/mock-providers';
import type { Meta } from '@storybook/react';

import OmnichannelBadges from './OmnichannelBadges';
import { createFakeSubscription } from '../../../../../tests/mocks/data';
import type { OmnichannelContextValue } from '../../../../contexts/OmnichannelContext';
import { OmnichannelContext } from '../../../../contexts/OmnichannelContext';

const meta = {
	component: OmnichannelBadges,
	parameters: {
		layout: 'centered',
	},
	args: {
		room: createFakeSubscription({ t: 'l' }) as unknown as ISubscription & IRoom,
	},
	decorators: [
		(Story) => {
			const AppRoot = mockAppRoot().build();

			const contextValue = {
				enabled: true,
				livechatPriorities: {
					enabled: true,
					data: [{ name: 'Highest', i18n: 'highest', sortItem: LivechatPriorityWeight.HIGHEST, dirty: false }],
				},
			} as OmnichannelContextValue;

			return (
				<OmnichannelContext.Provider value={contextValue}>
					<AppRoot>
						<Story />
					</AppRoot>
				</OmnichannelContext.Provider>
			);
		},
	],
} satisfies Meta<Omit<typeof OmnichannelBadges, 'room'>>;

export default meta;

export const WithPriority = {
	args: {
		room: createFakeSubscription({
			t: 'l',
			priorityWeight: LivechatPriorityWeight.HIGHEST,
		}),
	},
	parameters: {
	},
};
