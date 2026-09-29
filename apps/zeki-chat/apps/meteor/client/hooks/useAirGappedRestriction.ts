// Zeki: air-gapped restriction removed; never report restriction or warning phase,
// so the sidebar banner and restricted composer never render.
export const useAirGappedRestriction = (): [isRestrictionPhase: boolean, isWarningPhase: boolean, remainingDays: number] => {
	return [false, false, -1];
};
