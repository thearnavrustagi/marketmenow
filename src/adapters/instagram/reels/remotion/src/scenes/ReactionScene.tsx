import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { VisualProps } from "../schema";

export const ReactionScene: React.FC<{ visual: VisualProps }> = ({ visual }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const rawImage = (visual.image as string) ?? "";
  const imageSrc = rawImage ? staticFile(rawImage) : "";
  const reactionText = (visual.text_overlay as string) ?? "";

  const textScale = spring({
    frame: frame - Math.floor(fps * 0.2),
    fps,
    config: { damping: 10, stiffness: 150 },
  });

  return (
    <AbsoluteFill
      style={{
        background: "#1a1a2e",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      {imageSrc && (
        <Img
          src={imageSrc}
          style={{
            maxWidth: "85%",
            maxHeight: "55%",
            objectFit: "contain",
            borderRadius: 16,
            position: "absolute",
            top: "8%",
          }}
        />
      )}
      <div
        style={{
          position: "absolute",
          bottom: "10%",
          left: 0,
          right: 0,
          textAlign: "center",
          padding: "0 40px",
        }}
      >
        <div
          style={{
            transform: `scale(${textScale})`,
            color: "#ff6b6b",
            fontSize: 40,
            fontWeight: 800,
            fontFamily: "system-ui, sans-serif",
            textShadow: "0 3px 20px rgba(0,0,0,0.7)",
            background: "rgba(0,0,0,0.5)",
            borderRadius: 16,
            padding: "20px 30px",
            display: "inline-block",
          }}
        >
          {reactionText}
        </div>
      </div>
    </AbsoluteFill>
  );
};
