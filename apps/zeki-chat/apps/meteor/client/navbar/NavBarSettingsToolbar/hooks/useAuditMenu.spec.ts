import { mockAppRoot } from '@zeki.chat/mock-providers';
import { renderHook, waitFor } from '@testing-library/react';

import { useAuditMenu } from './useAuditMenu';

it('should return an empty array of items if doesn`t have capability', async () => {
	const { result } = renderHook(() => useAuditMenu(), {
		wrapper: mockAppRoot()
			.withEndpoint('GET', '/v1/capabilities.info', () => ({ capabilities: { modules: [] } }))
			.withJohnDoe()
			.withPermission('can-audit')
			.withPermission('can-audit-log')
			.build(),
	});

	await waitFor(() => expect(result.current.items).toEqual([]));
});

it('should return an empty array of items if have capability and not have permissions', async () => {
	const { result } = renderHook(() => useAuditMenu(), {
		wrapper: mockAppRoot()
			.withEndpoint('GET', '/v1/capabilities.info', () => ({ capabilities: { modules: ['auditing'] } }))
			.withMethod('capabilities:getModules', () => ['auditing'])
			.withJohnDoe()
			.build(),
	});

	await waitFor(() => expect(result.current.items).toEqual([]));
});

it('should return auditItems if have capability and permissions', async () => {
	const { result } = renderHook(() => useAuditMenu(), {
		wrapper: mockAppRoot()
			.withEndpoint('GET', '/v1/capabilities.info', () => ({ capabilities: { modules: ['auditing'] } }))
			.withJohnDoe()
			.withPermission('can-audit')
			.withPermission('can-audit-log')
			.build(),
	});

	await waitFor(() =>
		expect(result.current.items[0]).toEqual(
			expect.objectContaining({
				id: 'messages',
			}),
		),
	);

	expect(result.current.items[1]).toEqual(
		expect.objectContaining({
			id: 'auditLog',
		}),
	);
});

it('should return auditMessages item if have capability and can-audit permission', async () => {
	const { result } = renderHook(() => useAuditMenu(), {
		wrapper: mockAppRoot()
			.withEndpoint('GET', '/v1/capabilities.info', () => ({ capabilities: { modules: ['auditing'] } }))
			.withJohnDoe()
			.withPermission('can-audit')
			.build(),
	});

	await waitFor(() =>
		expect(result.current.items[0]).toEqual(
			expect.objectContaining({
				id: 'messages',
			}),
		),
	);
});

it('should return audiLogs item if have capability and can-audit-log permission', async () => {
	const { result } = renderHook(() => useAuditMenu(), {
		wrapper: mockAppRoot()
			.withEndpoint('GET', '/v1/capabilities.info', () => ({ capabilities: { modules: ['auditing'] } }))
			.withJohnDoe()
			.withPermission('can-audit-log')
			.build(),
	});

	await waitFor(() =>
		expect(result.current.items[0]).toEqual(
			expect.objectContaining({
				id: 'auditLog',
			}),
		),
	);
});

it('should return auditSecurityLog item if have capability and can-audit-log permission', async () => {
	const { result } = renderHook(() => useAuditMenu(), {
		wrapper: mockAppRoot()
			.withEndpoint('GET', '/v1/capabilities.info', () => ({ capabilities: { modules: ['auditing'] } }))
			.withJohnDoe()
			.withPermission('can-audit')
			.build(),
	});

	await waitFor(() =>
		expect(result.current.items[1]).toEqual(
			expect.objectContaining({
				id: 'auditSecurityLog',
			}),
		),
	);
});
