import type { HTMLAttributes, ReactElement, SVGAttributes } from 'react';

type RocketChatLogoProps = {
	color?: SVGAttributes<SVGSVGElement>['fill'];
};
export declare const RocketChatLogo: ({ color }?: RocketChatLogoProps) => ReactElement;

type TaggedRocketChatLogoProps = {
	tagTitle?: string;
	tagBackground?: string;
	color?: string;
} & HTMLAttributes<HTMLDivElement>;
export declare const TaggedRocketChatLogo: ({ tagTitle, tagBackground, color, ...props }?: TaggedRocketChatLogoProps) => ReactElement;
