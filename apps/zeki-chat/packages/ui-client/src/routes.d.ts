import '@zeki.chat/ui-contexts';

declare module '@zeki.chat/ui-contexts' {
	interface IRouterPaths {
		'setup-wizard': {
			pathname: `/setup-wizard${`/${string}` | ''}`;
			pattern: '/setup-wizard/:step?';
		};
	}
}
