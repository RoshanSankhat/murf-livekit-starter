import { useEffect } from 'react';
import { useRoomContext, useLocalParticipant } from '@livekit/components-react';
import { RoomEvent } from 'livekit-client';
import { toast } from 'sonner';

export function useAgentErrors() {
  const room = useRoomContext();
  const { microphoneTrack } = useLocalParticipant();

  // Function to execute the strict two-step check
  const evaluateMicrophoneState = async () => {
    // ------------------------------------------------------------------
    // STEP 1: Check if the Microphone is Disabled / Muted First
    // ------------------------------------------------------------------
    if (microphoneTrack?.isMuted) {
      toast.warning('Microphone is Disabled 🎙️', {
        description:
          'Your microphone is currently disabled or muted. Please click the microphone icon in the control bar to enable it.',
        duration: 6000,
      });
      return; // Stop here if it's just disabled/muted
    }

    // ------------------------------------------------------------------
    // STEP 2: Check if Microphone Access is Blocked in Browser Settings
    // ------------------------------------------------------------------
    try {
      if (navigator.permissions && navigator.permissions.query) {
        const permissionStatus = await navigator.permissions.query({
          name: 'microphone' as PermissionName,
        });

        if (permissionStatus.state === 'denied') {
          toast.error('Microphone Access Blocked 🔒', {
            description:
              'Microphone permission is blocked in your browser settings. Click the lock icon in the address bar to allow access and refresh.',
            duration: 8000,
          });
          return;
        }
      }
    } catch (err) {
      console.error('Error querying browser permissions:', err);
    }
  };

  // Trigger evaluation when LiveKit catches a media device failure
  useEffect(() => {
    if (!room) return;

    const handleMediaFailure = async (error: Error) => {
      console.error('Media failure captured:', error);
      await evaluateMicrophoneState();
    };

    room.on(RoomEvent.MediaDevicesError, handleMediaFailure);

    return () => {
      room.off(RoomEvent.MediaDevicesError, handleMediaFailure);
    };
  }, [room, microphoneTrack?.isMuted]);

  // Monitor dynamic mute/unmute actions during active call
  useEffect(() => {
    if (microphoneTrack?.isMuted) {
      toast.warning('Microphone is Disabled 🎙️', {
        description:
          'Your microphone is currently disabled or muted. Please click the microphone icon in the control bar to enable it.',
        duration: 5000,
      });
    }
  }, [microphoneTrack?.isMuted]);
}