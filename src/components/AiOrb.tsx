import clsx from 'clsx';
import { Sparkles } from 'lucide-react';

type AiOrbProps = {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
};

const sizes = {
  sm: 'h-8 w-8',
  md: 'h-10 w-10',
  lg: 'h-12 w-12',
};

const iconSizes = {
  sm: 'h-3.5 w-3.5',
  md: 'h-4 w-4',
  lg: 'h-5 w-5',
};

export default function AiOrb({ size = 'md', className }: AiOrbProps) {
  return (
    <div
      className={clsx(
        'flex shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 to-sky-400 text-white shadow-lg shadow-violet-200/50',
        sizes[size],
        className,
      )}
    >
      <Sparkles className={iconSizes[size]} />
    </div>
  );
}
