import clsx from 'clsx';
import nvidiaLogoSrc from '@/assets/nvidia-logo.png';

type Props = {
  className?: string;
  /** On dark surfaces, wrap logo in a white card so the official mark reads clearly. */
  variant?: 'dark' | 'light';
  framed?: boolean;
};

export default function NvidiaLogo({
  className = 'h-8 w-auto',
  variant = 'dark',
  framed,
}: Props) {
  const useFrame = framed ?? variant === 'dark';

  const img = (
    <img
      src={nvidiaLogoSrc}
      alt="NVIDIA"
      className={clsx('block object-contain', className)}
      loading="lazy"
      decoding="async"
      draggable={false}
    />
  );

  if (!useFrame) return img;

  return (
    <span className="nvidia-logo-frame inline-flex shrink-0 items-center justify-center rounded-lg bg-white px-2 py-1.5 shadow-sm">
      {img}
    </span>
  );
}
