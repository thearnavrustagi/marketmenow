import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { VisualProps } from "../schema";
import { GRADEASY_FONT } from "../fonts";

const BRAND_BLUE = "#4A8DF8";

export const GradeasyResponseScene: React.FC<{ visual: VisualProps }> = ({
  visual,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const responseText = (visual.text_overlay as string) ?? "I gotchu bro";

  const logoScale = spring({
    frame,
    fps,
    config: { damping: 12, stiffness: 150, mass: 0.6 },
  });

  const textEntry = spring({
    frame: Math.max(0, frame - 12),
    fps,
    config: { damping: 10, stiffness: 120 },
  });

  const textY = interpolate(textEntry, [0, 1], [50, 0]);
  const textOpacity = interpolate(textEntry, [0, 0.6], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: "#0A0A0A",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      {/* Gradeasy.ai logo */}
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
            fontFamily: GRADEASY_FONT,
          transform: `scale(${logoScale})`,
          marginBottom: 60,
        }}
      >
        <span
          style={{
            color: "#FFFFFF",
            fontSize: 80,
            fontWeight: 700,
            letterSpacing: -1,
          }}
        >
          Gradeasy
        </span>
        <span
          style={{
            color: BRAND_BLUE,
            fontSize: 80,
            fontWeight: 700,
            letterSpacing: -1,
          }}
        >
          .ai
        </span>
      </div>

      {/* Response text */}
      <div
        style={{
          color: "rgba(255,255,255,0.9)",
          fontSize: 48,
          fontWeight: 600,
            fontFamily: GRADEASY_FONT,
          textAlign: "center",
          lineHeight: 1.4,
          opacity: textOpacity,
          transform: `translateY(${textY}px)`,
          maxWidth: "85%",
          padding: "0 40px",
        }}
      >
        {responseText}
      </div>
    </AbsoluteFill>
  );
};
