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
import { BRAND_FONT } from "../fonts";

export const TransitionScene: React.FC<{ visual: VisualProps }> = ({
  visual,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const brandColor = (visual.brand_color as string) ?? "#4A8DF8";
  const frameBg = (visual.frame_background as string) ?? "#E0E0E0";

  const rawImage = (visual.image as string) ?? "";
  const imageSrc = rawImage ? staticFile(rawImage) : "";

  const imageScale = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 80, mass: 0.8 },
  });

  const imageY = interpolate(imageScale, [0, 1], [120, 0]);

  const panelSlide = spring({
    frame: Math.max(0, frame - 8),
    fps,
    config: { damping: 16, stiffness: 100, mass: 0.7 },
  });

  const panelY = interpolate(panelSlide, [0, 1], [200, 0]);
  const panelOpacity = interpolate(panelSlide, [0, 0.4], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: brandColor,
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      {/* Assignment image in gray frame */}
      {imageSrc && (
        <div
          style={{
            position: "absolute",
            top: "8%",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            width: "72%",
            height: "50%",
            background: frameBg,
            borderRadius: 8,
            padding: 24,
            transform: `translateY(${imageY}px) scale(${imageScale})`,
          }}
        >
          <Img
            src={imageSrc}
            style={{
              maxWidth: "100%",
              maxHeight: "100%",
              objectFit: "contain",
            }}
          />
        </div>
      )}

      {/* Dark bottom panel with brand name + suffix */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: "38%",
          background: (visual.panel_background as string) ?? "#0A0A0A",
          borderTopLeftRadius: Number(visual.panel_border_radius ?? 40),
          borderTopRightRadius: Number(visual.panel_border_radius ?? 40),
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          opacity: panelOpacity,
          transform: `translateY(${panelY}px)`,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            fontFamily: BRAND_FONT,
          }}
        >
          <span
            style={{
              color: "#FFFFFF",
              fontSize: Number(visual.brand_font_size ?? 64),
              fontWeight: 700,
              letterSpacing: -1,
            }}
          >
            {(visual.brand_name as string) ?? "BrandName"}
          </span>
          <span
            style={{
              color: brandColor,
              fontSize: Number(visual.brand_font_size ?? 64),
              fontWeight: 700,
              letterSpacing: -1,
            }}
          >
            {(visual.brand_suffix as string) ?? ".ai"}
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
