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

export const ReactionImageScene: React.FC<{ visual: VisualProps }> = ({
  visual,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const rawImage = (visual.reaction_image as string) ?? "";
  const imageSrc = rawImage ? staticFile(rawImage) : "";
  const reactionText = (visual.text_overlay as string) ?? "";

  const zoom = interpolate(frame, [0, fps * 2], [1, 1.15], {
    extrapolateRight: "clamp",
  });
  const imageOpacity = interpolate(frame, [0, fps * 0.2], [0, 1], {
    extrapolateRight: "clamp",
  });

  const textSpring = spring({
    frame: Math.max(0, frame - Math.floor(fps * 0.3)),
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
            position: "absolute",
            top: "5%",
            maxWidth: "90%",
            maxHeight: "60%",
            objectFit: "contain",
            borderRadius: 20,
            opacity: imageOpacity,
            transform: `scale(${zoom})`,
            boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
          }}
        />
      )}
      {reactionText && (
        <div
          style={{
            position: "absolute",
            bottom: "8%",
            left: 0,
            right: 0,
            textAlign: "center",
            padding: "0 40px",
          }}
        >
          <div
            style={{
              transform: `scale(${textSpring})`,
              color: "#ff6b6b",
              fontSize: 40,
              fontWeight: 800,
              fontFamily: "system-ui, sans-serif",
              textShadow: "0 3px 20px rgba(0,0,0,0.7)",
              background: "rgba(0,0,0,0.6)",
              borderRadius: 16,
              padding: "20px 30px",
              display: "inline-block",
            }}
          >
            {reactionText}
          </div>
        </div>
      )}
    </AbsoluteFill>
  );
};
