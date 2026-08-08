'use client';

import { useTheme } from 'next-themes';
import { AnimatePresence, motion } from 'motion/react';
import { useSessionContext, useVoiceAssistant } from '@livekit/components-react';
import type { AppConfig } from '@/app-config';
import { AgentSessionView_01 } from '@/components/agents-ui/blocks/agent-session-view-01';
import { WelcomeView } from '@/components/app/welcome-view';
import { AgentChatIndicator } from '@/components/agents-ui/agent-chat-indicator';

const MotionWelcomeView = motion.create(WelcomeView);
const MotionSessionView = motion.create(AgentSessionView_01);

const VIEW_MOTION_PROPS = {
  variants: {
    visible: { opacity: 1 },
    hidden: { opacity: 0 },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
  transition: { duration: 0.5, ease: 'linear' },
};

interface ViewControllerProps {
  appConfig: AppConfig;
}

export function ViewController({ appConfig }: ViewControllerProps) {
  const { isConnected, connectionState, start } = useSessionContext();
  const { state: agentState } = useVoiceAssistant();
  const { resolvedTheme } = useTheme();

  // 2. Connecting State
  if (connectionState === 'connecting') {
    return (
      <div className="fixed inset-0 flex flex-col items-center justify-center bg-black text-sky-100 z-50">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-sky-400 mb-4" />
        <h2 className="text-xl font-bold text-sky-100">Connecting to Alexa...</h2>
        <p className="text-sm font-medium mt-1 text-sky-200">
          Please wait while we set up your learning session.
        </p>
      </div>
    );
  }

  return (
    <AnimatePresence mode="wait">
      {/* 1 & 5. Ready & Call Ended View */}
      {!isConnected && (
        <MotionWelcomeView
          key="welcome"
          {...VIEW_MOTION_PROPS}
          startButtonText={appConfig.startButtonText || 'Start Learning Session'}
          onStartCall={start}
        />
      )}

      {/* 3 & 4. Active Call View with Clear Speaker Indicators */}
      {isConnected && (
        <div className="relative w-full h-full">
          {/* Floating Speaker Status Badge at Top Center */}
          <div className="fixed top-6 left-1/2 -translate-x-1/2 z-50 pointer-events-none">
            {agentState === 'listening' && (
              <AgentChatIndicator size="md" stateText="🎙️ Listening to you..." />
            )}
            {agentState === 'speaking' && (
              <AgentChatIndicator size="md" stateText="🔊 Alexa is speaking..." />
            )}
            {agentState === 'thinking' && (
              <AgentChatIndicator size="md" stateText="🤔 Alexa is thinking..." />
            )}
          </div>

          <MotionSessionView
            key="session-view"
            {...VIEW_MOTION_PROPS}
            supportsChatInput={appConfig.supportsChatInput}
            supportsVideoInput={appConfig.supportsVideoInput}
            supportsScreenShare={appConfig.supportsScreenShare}
            isPreConnectBufferEnabled={appConfig.isPreConnectBufferEnabled}
            audioVisualizerType={appConfig.audioVisualizerType}
            audioVisualizerColor={
              resolvedTheme === 'dark'
                ? appConfig.audioVisualizerColorDark
                : appConfig.audioVisualizerColor
            }
            audioVisualizerColorShift={appConfig.audioVisualizerColorShift}
            audioVisualizerBarCount={appConfig.audioVisualizerBarCount}
            audioVisualizerGridRowCount={appConfig.audioVisualizerGridRowCount}
            audioVisualizerGridColumnCount={appConfig.audioVisualizerGridColumnCount}
            audioVisualizerRadialBarCount={appConfig.audioVisualizerRadialBarCount}
            audioVisualizerRadialRadius={appConfig.audioVisualizerRadialRadius}
            audioVisualizerWaveLineWidth={appConfig.audioVisualizerWaveLineWidth}
            className="fixed inset-0"
          />
        </div>
      )}
    </AnimatePresence>
  );
}