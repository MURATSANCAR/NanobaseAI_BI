import clsx from 'clsx';
import NvidiaLogo from '@/components/NvidiaLogo';
import { NVIDIA_INCEPTION_COPY } from '@/constants/nvidiaInceptionCopy';

const INCEPTION_URL = 'https://www.nvidia.com/en-us/deep-learning-ai/startups/';

type Props = {
  variant?: 'pill' | 'featured';
  className?: string;
  linked?: boolean;
};

export default function NvidiaInceptionBadge({ variant = 'pill', className, linked = true }: Props) {
  const inner =
    variant === 'featured' ? (
      <div className={clsx('nvidia-inception-featured', className)}>
        <div className="nvidia-inception-featured-glow" aria-hidden />
        <div className="nvidia-inception-featured-logo" aria-hidden>
          <NvidiaLogo className="h-9 w-auto sm:h-10" variant="light" framed={false} />
        </div>
        <div className="nvidia-inception-featured-copy">
          <p className="nvidia-inception-featured-eyebrow">{NVIDIA_INCEPTION_COPY.eyebrow}</p>
          <p className="nvidia-inception-featured-title">{NVIDIA_INCEPTION_COPY.title}</p>
          <p className="nvidia-inception-featured-sub">{NVIDIA_INCEPTION_COPY.subtitle}</p>
        </div>
        <div className="nvidia-inception-featured-mark" aria-hidden>
          <span className="nvidia-inception-featured-mark-inner">INCEPTION</span>
        </div>
      </div>
    ) : (
      <span className={clsx('module-hero-nvidia-badge', className)} title={NVIDIA_INCEPTION_COPY.titleFull}>
        <NvidiaLogo className="h-7 w-auto sm:h-8" variant="dark" />
        <span className="module-hero-nvidia-divider" aria-hidden />
        <span className="nvidia-inception-pill-text">
          <span className="block text-[9px] font-bold uppercase tracking-[0.14em] text-[#76B900]">
            {NVIDIA_INCEPTION_COPY.eyebrow}
          </span>
          <span className="block text-[10px] font-semibold leading-tight text-white">
            {NVIDIA_INCEPTION_COPY.title}
          </span>
        </span>
      </span>
    );

  if (!linked) return inner;

  return (
    <a
      href={INCEPTION_URL}
      target="_blank"
      rel="noopener noreferrer"
      className="nvidia-inception-link inline-flex no-underline transition-opacity hover:opacity-95"
      aria-label={NVIDIA_INCEPTION_COPY.titleFull}
    >
      {inner}
    </a>
  );
}
