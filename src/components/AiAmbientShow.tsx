import clsx from 'clsx';
import type { LucideIcon } from 'lucide-react';
import {
  BarChart3,
  Bot,
  BrainCircuit,
  Cpu,
  LineChart,
  Sparkles,
  TestTube2,
  Zap,
} from 'lucide-react';
import { t } from '@/i18n';

export type AiAmbientVariant = 'home' | 'bi' | 'test';

type OrbSpec = {
  Icon: LucideIcon;
  className: string;
  animation: string;
  size: string;
};

type WordSpec = {
  key: string;
  className: string;
  animation: string;
};

type VariantConfig = {
  blobA: string;
  blobB: string;
  blobC: string;
  meshStroke: string;
  orbFrom: string;
  orbTo: string;
  wordTone: string;
  wordKeys: string[];
  orbs: Omit<OrbSpec, 'Icon'>[];
  orbIcons: LucideIcon[];
  words: Omit<WordSpec, 'key'>[];
};

const VARIANTS: Record<AiAmbientVariant, VariantConfig> = {
  home: {
    blobA: 'bg-violet-400/30',
    blobB: 'bg-sky-400/25',
    blobC: 'bg-fuchsia-400/20',
    meshStroke: 'rgba(124, 58, 237, 0.18)',
    orbFrom: 'from-violet-500',
    orbTo: 'to-sky-400',
    wordTone: 'text-violet-600/80',
    wordKeys: ['home.word1', 'home.word2', 'home.word3', 'home.word4', 'home.word5', 'home.word6'],
    orbIcons: [BrainCircuit, Sparkles, Bot, Cpu],
    orbs: [
      { className: 'left-[5%] top-[28%]', animation: 'animate-float', size: 'h-14 w-14 sm:h-16 sm:w-16' },
      { className: 'right-[6%] top-[34%]', animation: 'animate-float-delayed', size: 'h-12 w-12 sm:h-14 sm:w-14' },
      { className: 'left-[26%] bottom-[12%]', animation: 'animate-float-slow', size: 'h-10 w-10 sm:h-12 sm:w-12' },
      { className: 'right-[22%] top-[10%]', animation: 'animate-orbit', size: 'h-11 w-11 sm:h-12 sm:w-12' },
      { className: 'left-[48%] top-[6%]', animation: 'animate-float-delayed', size: 'h-9 w-9 sm:h-10 sm:w-10' },
      { className: 'right-[40%] bottom-[8%]', animation: 'animate-orbit-reverse', size: 'h-10 w-10 sm:h-11 sm:w-11' },
    ],
    words: [
      { className: 'left-[7%] top-[16%]', animation: 'animate-float-slow' },
      { className: 'right-[10%] top-[20%]', animation: 'animate-float-delayed' },
      { className: 'left-[12%] bottom-[26%]', animation: 'animate-float' },
      { className: 'right-[16%] bottom-[30%]', animation: 'animate-float-slow' },
      { className: 'left-[40%] top-[10%]', animation: 'animate-float-delayed' },
      { className: 'right-[36%] bottom-[16%]', animation: 'animate-float' },
    ],
  },
  bi: {
    blobA: 'bg-sky-400/28',
    blobB: 'bg-indigo-400/22',
    blobC: 'bg-cyan-400/18',
    meshStroke: 'rgba(14, 165, 233, 0.2)',
    orbFrom: 'from-sky-500',
    orbTo: 'to-indigo-500',
    wordTone: 'text-sky-700/80',
    wordKeys: [
      'ambient.bi.word1',
      'ambient.bi.word2',
      'ambient.bi.word3',
      'ambient.bi.word4',
      'ambient.bi.word5',
      'ambient.bi.word6',
    ],
    orbIcons: [BarChart3, LineChart, BrainCircuit, Cpu, Sparkles],
    orbs: [
      { className: 'left-[3%] top-[22%]', animation: 'animate-float-delayed', size: 'h-12 w-12 sm:h-14 sm:w-14' },
      { className: 'right-[4%] top-[16%]', animation: 'animate-orbit', size: 'h-11 w-11 sm:h-14 sm:w-14' },
      { className: 'left-[18%] bottom-[14%]', animation: 'animate-orbit-reverse', size: 'h-10 w-10 sm:h-12 sm:w-12' },
      { className: 'right-[16%] bottom-[22%]', animation: 'animate-float-slow', size: 'h-12 w-12 sm:h-14 sm:w-14' },
      { className: 'left-[42%] top-[8%]', animation: 'animate-float', size: 'h-9 w-9 sm:h-10 sm:w-10' },
      { className: 'right-[36%] top-[48%]', animation: 'animate-float-delayed', size: 'h-10 w-10' },
    ],
    words: [
      { className: 'left-[6%] top-[12%]', animation: 'animate-float-slow' },
      { className: 'right-[8%] top-[36%]', animation: 'animate-float' },
      { className: 'left-[10%] bottom-[24%]', animation: 'animate-float-delayed' },
      { className: 'right-[12%] bottom-[10%]', animation: 'animate-float-slow' },
      { className: 'left-[34%] top-[28%]', animation: 'animate-float' },
      { className: 'right-[30%] bottom-[34%]', animation: 'animate-float-delayed' },
    ],
  },
  test: {
    blobA: 'bg-violet-400/28',
    blobB: 'bg-fuchsia-400/22',
    blobC: 'bg-purple-400/18',
    meshStroke: 'rgba(139, 92, 246, 0.22)',
    orbFrom: 'from-violet-500',
    orbTo: 'to-fuchsia-500',
    wordTone: 'text-violet-700/80',
    wordKeys: [
      'ambient.test.word1',
      'ambient.test.word2',
      'ambient.test.word3',
      'ambient.test.word4',
      'ambient.test.word5',
      'ambient.test.word6',
    ],
    orbIcons: [Zap, TestTube2, Bot, BrainCircuit, Cpu],
    orbs: [
      { className: 'left-[4%] top-[20%]', animation: 'animate-orbit-reverse', size: 'h-12 w-12 sm:h-14 sm:w-14' },
      { className: 'right-[5%] top-[28%]', animation: 'animate-float', size: 'h-11 w-11 sm:h-14 sm:w-14' },
      { className: 'left-[22%] bottom-[12%]', animation: 'animate-float-delayed', size: 'h-10 w-10 sm:h-12 sm:w-12' },
      { className: 'right-[20%] bottom-[16%]', animation: 'animate-orbit', size: 'h-12 w-12 sm:h-14 sm:w-14' },
      { className: 'left-[46%] top-[6%]', animation: 'animate-float-slow', size: 'h-9 w-9 sm:h-10 sm:w-10' },
      { className: 'right-[34%] top-[44%]', animation: 'animate-float', size: 'h-10 w-10' },
    ],
    words: [
      { className: 'left-[7%] top-[32%]', animation: 'animate-float-delayed' },
      { className: 'right-[7%] top-[14%]', animation: 'animate-float-slow' },
      { className: 'left-[11%] bottom-[30%]', animation: 'animate-float' },
      { className: 'right-[13%] bottom-[6%]', animation: 'animate-float-delayed' },
      { className: 'left-[38%] top-[18%]', animation: 'animate-float' },
      { className: 'right-[28%] bottom-[26%]', animation: 'animate-float-slow' },
    ],
  },
};

const SPARKLES = [
  { className: 'left-[15%] top-[8%] animate-sparkle', delay: '0s' },
  { className: 'left-[72%] top-[14%] animate-sparkle', delay: '0.8s' },
  { className: 'left-[88%] top-[55%] animate-sparkle', delay: '1.4s' },
  { className: 'left-[28%] top-[72%] animate-sparkle', delay: '0.3s' },
  { className: 'left-[55%] top-[82%] animate-sparkle', delay: '1.1s' },
  { className: 'left-[8%] top-[58%] animate-sparkle', delay: '1.7s' },
  { className: 'left-[92%] top-[32%] animate-sparkle', delay: '0.5s' },
  { className: 'left-[62%] top-[6%] animate-sparkle', delay: '2s' },
] as const;

function NeuralMesh({ stroke }: { stroke: string }) {
  return (
    <svg
      className="ai-neural-mesh absolute inset-0 h-full w-full"
      viewBox="0 0 1200 800"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden
    >
      <defs>
        <linearGradient id="neuralGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.6" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0.15" />
        </linearGradient>
      </defs>
      {[
        'M80,120 Q300,40 520,180 T920,100',
        'M60,400 Q280,320 500,420 T1000,360',
        'M120,650 Q400,560 680,620 T1100,540',
        'M200,80 L420,220 L640,90 L860,240',
        'M150,500 L380,380 L600,520 L820,400 L1050,480',
      ].map((d, i) => (
        <path
          key={d}
          d={d}
          fill="none"
          stroke="url(#neuralGrad)"
          strokeWidth={i < 3 ? 1.5 : 1}
          className="ai-neural-line"
          style={{ animationDelay: `${i * 0.6}s` }}
        />
      ))}
      {[
        [80, 120],
        [520, 180],
        [920, 100],
        [60, 400],
        [500, 420],
        [200, 80],
        [420, 220],
        [640, 90],
        [150, 500],
        [600, 520],
        [1050, 480],
      ].map(([cx, cy], i) => (
        <circle
          key={`${cx}-${cy}`}
          cx={cx}
          cy={cy}
          r={i % 3 === 0 ? 4 : 3}
          fill={stroke}
          className="ai-neural-node"
          style={{ animationDelay: `${i * 0.25}s` }}
        />
      ))}
    </svg>
  );
}

function FloatingOrb({
  Icon,
  className,
  animation,
  size,
  from,
  to,
}: OrbSpec & { from: string; to: string }) {
  return (
    <div
      className={clsx(
        'ai-floating-orb pointer-events-none absolute flex items-center justify-center rounded-full bg-gradient-to-br text-white shadow-lg',
        `bg-gradient-to-br ${from} ${to}`,
        from === 'from-emerald-500' ? 'shadow-emerald-300/40' : from === 'from-sky-500' ? 'shadow-sky-300/40' : from === 'from-violet-500' ? 'shadow-violet-300/40' : 'shadow-violet-300/40',
        size,
        animation,
        className,
      )}
      aria-hidden
    >
      <div className="ai-orb-pulse absolute inset-0 rounded-full" />
      <Icon className="relative z-10 h-[42%] w-[42%] opacity-95" />
    </div>
  );
}

type Props = {
  variant?: AiAmbientVariant;
  intensity?: 'subtle' | 'full';
  /**
   * Opt-in for the legacy infinite animations. Default is a STATIC scene —
   * identical gradients/blobs/mesh, zero continuous compositing work at idle.
   */
  animated?: boolean;
};

export default function AiAmbientShow({ variant = 'test', intensity = 'full', animated = false }: Props) {
  const cfg = VARIANTS[variant];
  const subtle = intensity === 'subtle';

  return (
    <div
      className={clsx(
        'pointer-events-none fixed inset-0 z-0 overflow-hidden motion-reduce:opacity-40',
        subtle && 'opacity-70',
        !animated && 'ai-ambient-static',
      )}
      aria-hidden
    >
      <div className={clsx('ai-aurora absolute -left-40 -top-32 h-[28rem] w-[28rem] rounded-full blur-3xl', cfg.blobA)} />
      <div className={clsx('ai-aurora-reverse absolute -right-40 bottom-0 h-[26rem] w-[26rem] rounded-full blur-3xl', cfg.blobB)} />
      <div className={clsx('ai-aurora absolute left-1/3 top-1/2 h-80 w-80 -translate-x-1/2 rounded-full blur-3xl', cfg.blobC)} />

      {!subtle && <NeuralMesh stroke={cfg.meshStroke} />}

      <div className="ai-scanline absolute inset-0" />

      {cfg.orbs.map((orb, i) => (
        <FloatingOrb
          key={`orb-${i}`}
          Icon={cfg.orbIcons[i % cfg.orbIcons.length]}
          className={orb.className}
          animation={orb.animation}
          size={orb.size}
          from={cfg.orbFrom}
          to={cfg.orbTo}
        />
      ))}

      {cfg.words.map((word, i) => (
        <span
          key={cfg.wordKeys[i]}
          className={clsx(
            'ai-float-word pointer-events-none absolute',
            cfg.wordTone,
            word.animation,
            word.className,
            subtle && 'hidden sm:inline-flex',
          )}
        >
          {t(cfg.wordKeys[i])}
        </span>
      ))}

      {!subtle &&
        SPARKLES.map(({ className, delay }, i) => (
          <span
            key={`sparkle-${i}`}
            className={clsx('ai-sparkle absolute', className)}
            style={{ animationDelay: delay }}
          />
        ))}
    </div>
  );
}

export function resolveAmbientVariant(pathname: string): AiAmbientVariant {
  if (pathname.startsWith('/bi')) return 'bi';
  if (pathname.startsWith('/contracts')) return 'home';
  if (pathname.startsWith('/test')) return 'test';
  if (
    pathname.startsWith('/projects') ||
    pathname.startsWith('/environment') ||
    pathname.startsWith('/repositories') ||
    pathname.startsWith('/analysis') ||
    pathname.startsWith('/run') ||
    pathname.startsWith('/suites') ||
    pathname.startsWith('/registry') ||
    pathname.startsWith('/reports')
  ) {
    return 'test';
  }
  if (pathname.startsWith('/settings') || pathname.startsWith('/users')) return 'home';
  if (pathname === '/' || pathname === '') return 'home';
  return 'test';
}
