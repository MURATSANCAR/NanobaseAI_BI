import { mockAppRoot } from '@zeki.chat/mock-providers';
import type { Decorator } from '@storybook/react';

import ModalContextMock from '../client/stories/contexts/ModalContextMock';
import RouterContextMock from '../client/stories/contexts/RouterContextMock';
import ServerContextMock from '../client/stories/contexts/ServerContextMock';
import TranslationContextMock from '../client/stories/contexts/TranslationContextMock';

const MockedAppRoot = mockAppRoot().build();

export const zekiChatDecorator: Decorator = (fn, { parameters }) => {
	require('../app/theme/client/main.css');
	require('../app/theme/client/zekichat.font.css');

	return (
		<MockedAppRoot>
			<ServerContextMock {...parameters.serverContext}>
				<TranslationContextMock {...parameters.translationContext}>
					<ModalContextMock {...parameters.modalContext}>
						<RouterContextMock {...parameters.routerContext}>
							<style>{`
								body {
									background-color: white;
								}
							`}</style>
							<div className='color-primary-font-color'>{fn()}</div>
						</RouterContextMock>
					</ModalContextMock>
				</TranslationContextMock>
			</ServerContextMock>
		</MockedAppRoot>
	);
};
