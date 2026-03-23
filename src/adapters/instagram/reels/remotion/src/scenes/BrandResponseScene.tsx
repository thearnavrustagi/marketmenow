import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { VisualProps } from "../schema";
import { BRAND_FONT } from "../fonts";

export const BrandResponseScene: React.FC<{ visual: VisualProps }> = ({
  visual,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const BRAND_BLUE = (visual.brand_color as string) ?? "#4A8DF8";
  const brandName = (visual.brand_name as string) ?? "BrandName";
  const brandSuffix = (visual.brand_suffix as string) ?? ".ai";
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
        background: (visual.background as string) ?? "#0A0A0A",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      {/* Brand logo */}
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
            fontFamily: BRAND_FONT,
          transform: `scale(${logoScale})`,
          marginBottom: 60,
        }}
      >
        <span
          style={{
            color: "#FFFFFF",
            fontSize: Number(visual.brand_font_size ?? 80),
            fontWeight: 700,
            letterSpacing: -1,
          }}
        >
          {brandName}
        </span>
        <span
          style={{
            color: BRAND_BLUE,
            fontSize: Number(visual.brand_font_size ?? 80),
            fontWeight: 700,
            letterSpacing: -1,
          }}
        >
          {brandSuffix}
        </span>
      </div>

      {/* Response text */}
      <div
        style={{
          color: (visual.text_color as string) ?? "rgba(255,255,255,0.9)",
          fontSize: Number(visual.font_size ?? 48),
          fontWeight: Number(visual.font_weight ?? 600),
            fontFamily: BRAND_FONT,
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
