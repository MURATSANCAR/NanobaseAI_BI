import clsx from 'clsx';
import nanobaseLogoSrc from '@/assets/nanobaseai-logo.svg';
import { DEFAULT_PORTAL_BRAND } from '@/utils/portalBranding';

type Props = {
  className?: string;
  alt?: string;
};

export default function NanobaseLogo({
  className = 'h-8 w-auto',
  alt = DEFAULT_PORTAL_BRAND,
}: Props) {
  return (
    <img
      src={nanobaseLogoSrc}
      alt={alt}
      className={clsx('block object-contain', className)}
      loading="lazy"
      decoding="async"
      draggable={false}
    />
  );
}
