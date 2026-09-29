import EventEmitter from 'node:events';

const WARNING_PERIOD_IN_DAYS = 7;

// Zeki: air-gapped restriction disabled. The workspace is never restricted and no
// stats token from collector.rocket.chat is required. Public API kept for callers.
class AirGappedRestrictionClass extends EventEmitter {
	#restricted = false;

	public get restricted(): boolean {
		return this.#restricted;
	}

	public async computeRestriction(_encryptedToken?: string): Promise<void> {
		// Zeki: always emit the "no restriction" signal (days: -1).
		this.#restricted = false;
		this.emit('remainingDays', { days: -1 });
	}

	public isWarningPeriod(days: number) {
		if (days < 0) {
			return false;
		}
		return days <= WARNING_PERIOD_IN_DAYS;
	}
}

const airGappedRestriction = new AirGappedRestrictionClass();

export { airGappedRestriction as AirGappedRestriction };
