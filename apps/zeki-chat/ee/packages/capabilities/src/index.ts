import { CoreModules } from '@zeki.chat/core-typings';
import type { CapabilityModule } from '@zeki.chat/core-typings';

type Callback = () => unknown;
type ModuleChange = { module: CapabilityModule; external: boolean; valid: boolean };

/** Local implementation availability. This is not an entitlement or a subscription. */
export class CapabilityRegistry {
	private ready = false;
	private readonly readyCallbacks = new Set<Callback>();
	private readonly featureCallbacks = new Map<CapabilityModule, Set<Callback>>();
	private readonly moduleCallbacks = new Set<(event: ModuleChange) => void>();
	private readonly modules = new Set<CapabilityModule>();

	initialize(): void {
		if (this.ready) return;
		const queuedFeatures = new Map([...this.featureCallbacks].map(([module, callbacks]) => [module, [...callbacks]]));
		const queuedReady = [...this.readyCallbacks];
		for (const module of CoreModules) this.modules.add(module);
		this.ready = true;
		for (const module of this.modules) {
			for (const cb of this.moduleCallbacks) cb({ module, external: false, valid: true });
			for (const cb of queuedFeatures.get(module) || []) this.invoke(cb);
		}
		for (const cb of queuedReady) this.invoke(cb);
	}

	private invoke(cb: Callback): void {
		try { Promise.resolve(cb()).catch((error) => console.error('Capability initialization failed', error)); }
		catch (error) { console.error('Capability initialization failed', error); }
	}

	isReady(): boolean { return this.ready; }
	hasModule(module: string): boolean { return this.modules.has(module as CapabilityModule); }
	getModules(): CapabilityModule[] { return [...this.modules]; }

	onReady(cb: Callback): () => void {
		this.readyCallbacks.add(cb);
		if (this.ready) this.invoke(cb);
		return () => { this.readyCallbacks.delete(cb); };
	}

	onFeature(module: CapabilityModule, cb: Callback): () => void {
		const callbacks = this.featureCallbacks.get(module) || new Set<Callback>();
		callbacks.add(cb);
		this.featureCallbacks.set(module, callbacks);
		if (this.hasModule(module)) this.invoke(cb);
		return () => { callbacks.delete(cb); };
	}

	whenFeature(module: CapabilityModule, cb: Callback): unknown {
		if (this.hasModule(module)) return cb();
		this.onFeature(module, cb);
		return undefined;
	}

	onUnavailableFeature(module: CapabilityModule, cb: Callback): () => void {
		return this.onReady(() => { return !this.hasModule(module) ? cb() : undefined; });
	}

	onToggledFeature(module: CapabilityModule, { up, down }: { up?: Callback; down?: Callback }): () => void {
		return this.onReady(() => this.hasModule(module) ? up?.() : down?.());
	}

	onModule(cb: (event: ModuleChange) => void): () => void {
		this.moduleCallbacks.add(cb);
		return () => { this.moduleCallbacks.delete(cb); };
	}

	async overwriteClassOnFeature(module: CapabilityModule, original: { new (...args: any[]): any }, overrides: Record<string, (...args: any[]) => any>): Promise<void> {
		await this.whenFeature(module, () => {
			for (const [key, implementation] of Object.entries(overrides)) {
				const previous = original.prototype[key];
				original.prototype[key] = function (...args: any[]) { return implementation.call(this, previous, ...args); };
			}
		});
	}
}

export const Capabilities = new CapabilityRegistry();
