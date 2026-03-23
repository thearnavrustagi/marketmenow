import {
  AbsoluteFill,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { VisualProps } from "../schema";
import { BRAND_FONT } from "../fonts";

export const SegmentationScene: React.FC<{ visual: VisualProps }> = ({
  visual,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const brandColor = (visual.brand_color as string) ?? "#4A8DF8";
  const frameBg = (visual.frame_background as string) ?? "#E0E0E0";

  const rawImage = (visual.image as string) ?? "";
  const imageSrc = rawImage ? staticFile(rawImage) : "";

  const scanLineProgress = interpolate(
    frame,
    [0, durationInFrames * 0.8],
    [0, 100],
    { extrapolateRight: "clamp" },
  );

  const dotCount = 3;
  const dotCycle = Math.floor((frame / 8) % (dotCount + 1));
  const dots = ".".repeat(dotCycle);

  const pulseOpacity = interpolate(
    Math.sin((frame / fps) * Math.PI * 2),
    [-1, 1],
    [0.4, 1],
  );

  return (
    <AbsoluteFill style={{ background: brandColor }}>
      {/* Assignment image in gray frame — matching TransitionScene layout */}
      {imageSrc && (
        <div
          style={{
            position: "absolute",
            top: "8%",
            left: "50%",
            transform: "translateX(-50%)",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            width: "72%",
            height: "50%",
            background: frameBg,
            borderRadius: 8,
            padding: 24,
            overflow: "hidden",
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

          {/* Scan line overlay */}
          <div
            style={{
              position: "absolute",
              top: `${scanLineProgress}%`,
              left: 0,
              width: "100%",
              height: 3,
              background: `linear-gradient(90deg, transparent, ${brandColor}, transparent)`,
              boxShadow: `0 0 16px ${brandColor}, 0 0 32px rgba(74,141,248,0.3)`,
              opacity: scanLineProgress < 98 ? 0.95 : 0,
            }}
          />
        </div>
      )}

      {/* Dark bottom panel with brand name + status */}
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
          gap: 20,
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
        <div
          style={{
            color: "rgba(255,255,255,0.7)",
            fontSize: Number(visual.status_font_size ?? 28),
            fontWeight: 500,
            fontFamily: BRAND_FONT,
            letterSpacing: 0.5,
            opacity: pulseOpacity,
            minWidth: 360,
            textAlign: "center",
          }}
        >
          {`${(visual.status_text as string) ?? "Analyzing assignment"}${dots}`}
        </div>
      </div>
    </AbsoluteFill>
  );
};
