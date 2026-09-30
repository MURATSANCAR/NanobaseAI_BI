jest.mock('../lib/meteorRuntimeConfig', () => ({ getRootUrlPathPrefix: () => '/timas/sohbet' }));
jest.mock('../lib/appLayout', () => ({ appLayout: { render: jest.fn() } }));
jest.mock('../lib/rooms/roomCoordinator', () => ({ roomCoordinator: {} }));

// eslint-disable-next-line import/first
import { Router } from './index';

describe('Router under a sub-path', () => {
	const router = new Router();

	it('prefixes plain paths so history never points at the site root', () => {
		expect(router.buildRoutePath('/home')).toBe('/timas/sohbet/home');
		expect(router.buildRoutePath({ pathname: '/directory/channels', search: { q: 'a' } })).toBe('/timas/sohbet/directory/channels?q=a');
	});

	it('leaves paths that already carry the prefix, relative paths and the base itself alone', () => {
		expect(router.buildRoutePath('/timas/sohbet/home')).toBe('/timas/sohbet/home');
		expect(router.buildRoutePath('/timas/sohbet')).toBe('/timas/sohbet');
		expect(router.buildRoutePath('home')).toBe('home');
	});

	it('keeps pattern routes prefixed once', () => {
		expect(router.buildRoutePath({ pattern: '/channel/:name', params: { name: 'genel' } })).toBe('/timas/sohbet/channel/genel');
	});
});
