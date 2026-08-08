import { type ComponentProps, type Ref } from 'react';
import { type VariantProps, cva } from 'class-variance-authority';
import { type MotionProps, motion } from 'motion/react';
import { cn } from '@/lib/shadcn/utils';

const motionAnimationProps = {
  variants: {
    hidden: {
      opacity: 0,
      scale: 0.1,
      transition: {
        duration: 0.1,
        ease: 'linear' as const,
      },
    },
    visible: {
      opacity: [0.5, 1],
      scale: [1, 1.2],
      transition: {
        type: 'spring' as const,
        bounce: 0,
        duration: 0.5,
        repeat: Infinity,
        repeatType: 'mirror' as const,
      },
    },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
};

const agentChatIndicatorVariants = cva('inline-block size-2.5 rounded-full bg-sky-400', {
  variants: {
    size: {
      sm: 'size-2.5',
      md: 'size-4',
      lg: 'size-6',
    },
  },
  defaultVariants: {
    size: 'md',
  },
});

export interface AgentChatIndicatorProps extends MotionProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
  stateText?: string;
  ref?: Ref<HTMLSpanElement>;
}

export function AgentChatIndicator({
  size = 'md',
  className,
  stateText = 'Alexa is active...',
  ...props
}: AgentChatIndicatorProps &
  ComponentProps<'span'> &
  VariantProps<typeof agentChatIndicatorVariants>) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-sky-500/30 bg-black/60 backdrop-blur-sm">
      <motion.span
        {...motionAnimationProps}
        transition={{ duration: 0.1, ease: 'linear' as const }}
        className={cn(agentChatIndicatorVariants({ size }), className)}
        style={{ backgroundColor: '#38bdf8' }}
        {...props}
      />
      <span className="text-xs font-semibold tracking-wide" style={{ color: '#e0f2fe' }}>
        {stateText}
      </span>
    </div>
  );
}