import type { HTMLAttributes, ReactElement, SVGAttributes } from 'react';

type ZekiChatLogoProps = {
	color?: SVGAttributes<SVGSVGElement>['fill'];
};
export declare const ZekiChatLogo: ({ color }?: ZekiChatLogoProps) => ReactElement;

type TaggedZekiChatLogoProps = {
	tagTitle?: string;
	tagBackground?: string;
	color?: string;
} & HTMLAttributes<HTMLDivElement>;
export declare const TaggedZekiChatLogo: ({ tagTitle, tagBackground, color, ...props }?: TaggedZekiChatLogoProps) => ReactElement;
