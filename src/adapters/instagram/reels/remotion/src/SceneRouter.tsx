import { AbsoluteFill, Audio, OffthreadVideo, Series, staticFile, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { BeatProps, ReelProps, VisualProps } from "./schema";
import { TransitionWrapper } from "./transitions";
import {
  BrandCTAScene,
  BrandResponseScene,
  CustomScene,
  FlashRevealScene,
  GradingScene,
  HookScene,
  ReactionImageScene,
  ReactionScene,
  RedditStoryScene,
  ResultScene,
  RevealScene,
  RoastScene,
  RubricScene,
  SegmentationScene,
  TikTokCommentScene,
  TransitionScene,
} from "./scenes";

type SceneComponent = React.FC<{ visual: VisualProps }>;

const SCENE_MAP: Record<string, SceneComponent> = {
  HookScene,
  RevealScene,
  ReactionScene,
  ReactionImageScene,
  TikTokCommentScene,
  FlashRevealScene,
  RoastScene,
  BrandResponseScene,
  GradeasyResponseScene: BrandResponseScene, // backward compat alias
  SegmentationScene,
  TransitionScene,
  RubricScene,
  GradingScene,
  ResultScene,
  CustomScene,
  RedditStoryScene,
  BrandCTAScene,
};

const WORDS_PER_CHUNK = 5;
const EFFECTIVE_WPM = 187;

function chunkWords(text: string): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  const chunks: string[] = [];
  for (let i = 0; i < words.length; i += WORDS_PER_CHUNK) {
    chunks.push(words.slice(i, i + WORDS_PER_CHUNK).join(" "));
  }
  return chunks.length > 0 ? chunks : [""];
}

const Subtitle: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  if (!text) return null;

  const chunks = chunkWords(text);
  const framesPerChunk = Math.round(
    (WORDS_PER_CHUNK / EFFECTIVE_WPM) * 60 * fps
  );

  const currentIdx = Math.min(
    Math.floor(frame / framesPerChunk),
    chunks.length - 1
  );
  const currentChunk = chunks[currentIdx];

  const chunkLocalFrame = frame - currentIdx * framesPerChunk;
  const popIn = interpolate(chunkLocalFrame, [0, 3], [0.92, 1], {
    extrapolateRight: "clamp",
  });
  const fadeIn = interpolate(chunkLocalFrame, [0, 3], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        bottom: 140,
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        zIndex: 100,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          background: "rgba(0, 0, 0, 0.82)",
          borderRadius: 16,
          padding: "16px 30px",
          maxWidth: "90%",
          opacity: fadeIn,
          transform: `scale(${popIn})`,
          backdropFilter: "blur(8px)",
        }}
      >
        <div
          style={{
            color: "#fff",
            fontSize: 36,
            fontWeight: 800,
            fontFamily: "'DM Sans', system-ui, sans-serif",
            textAlign: "center",
            lineHeight: 1.4,
            textShadow: "0 2px 8px rgba(0,0,0,0.7)",
          }}
        >
          {currentChunk}
        </div>
      </div>
    </div>
  );
};

export const SceneRouter: React.FC<ReelProps> = ({ beats }) => {
  const firstVisual = beats.length > 0 ? beats[0].visual : {};
  const bgVideo = (firstVisual.background_video as string) ?? "";
  const bgMusic = (firstVisual.background_music as string) ?? "";

  return (
    <AbsoluteFill>
      {/* Shared continuous background video layer */}
      {bgVideo && (
        <OffthreadVideo
          src={staticFile(bgVideo)}
          muted
          style={{
            position: "absolute",
            width: "100%",
            height: "100%",
            objectFit: "cover",
            zIndex: 0,
          }}
        />
      )}

      {/* Background music at low volume */}
      {bgMusic && (
        <Audio src={staticFile(bgMusic)} volume={0.2} loop />
      )}

      {/* Beat scenes layered on top */}
      <Series>
        {beats.map((beat) => {
          const Scene = SCENE_MAP[beat.scene];
          if (!Scene) {
            console.warn(`Unknown scene: ${beat.scene}`);
            return null;
          }

          return (
            <Series.Sequence
              key={beat.id}
              durationInFrames={beat.durationFrames}
            >
              <TransitionWrapper
                entryTransition={beat.entryTransition}
                exitTransition={beat.exitTransition}
                durationFrames={beat.durationFrames}
              >
                <Scene visual={beat.visual} />
              </TransitionWrapper>
              {beat.subtitle && <Subtitle text={beat.subtitle} />}
              {beat.audioSrc && (
                <Audio src={staticFile(beat.audioSrc)} volume={1} />
              )}
            </Series.Sequence>
          );
        })}
      </Series>
    </AbsoluteFill>
  );
};
