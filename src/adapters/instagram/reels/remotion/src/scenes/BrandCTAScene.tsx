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

export const BrandCTAScene: React.FC<{ visual: VisualProps }> = ({ visual }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const brandName = (visual.brand_name as string) ?? "Brand";
  const brandSuffix = (visual.brand_suffix as string) ?? "";
  const brandColor = (visual.brand_color as string) ?? "#4A8DF8";
  const logoImage = (visual.logo_image as string) ?? "";
  const ctaText = (visual.cta_text as string) ?? "";

  const logoSpring = spring({ frame, fps, config: { damping: 12, stiffness: 80 } });
  const logoScale = interpolate(logoSpring, [0, 1], [0.5, 1]);
  const logoOpacity = interpolate(logoSpring, [0, 1], [0, 1]);

  const textDelay = Math.round(fps * 0.3);
  const textFrame = Math.max(0, frame - textDelay);
  const textSpring = spring({ frame: textFrame, fps, config: { damping: 14, stiffness: 100 } });
  const textOpacity = interpolate(textSpring, [0, 1], [0, 1]);
  const textY = interpolate(textSpring, [0, 1], [30, 0]);

  return (
    <AbsoluteFill
      style={{
        background: "#000",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 40,
      }}
    >
      {/* Brand name as logo */}
      <div
        style={{
          opacity: logoOpacity,
          transform: `scale(${logoScale})`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {logoImage ? (
          <Img
            src={staticFile(logoImage)}
            style={{ height: 120, objectFit: "contain" }}
          />
        ) : (
          <div
            style={{
              fontSize: 72,
              fontWeight: 700,
              color: "#fff",
              fontFamily: BRAND_FONT,
            }}
          >
            {brandName}
            <span style={{ color: brandColor }}>{brandSuffix}</span>
          </div>
        )}
      </div>

      {/* CTA link in monospace */}
      {ctaText && (
        <div
          style={{
            opacity: textOpacity,
            transform: `translateY(${textY}px)`,
            color: "rgba(255, 255, 255, 0.5)",
            fontSize: 28,
            fontWeight: 400,
            fontFamily: "'SF Mono', 'Fira Code', 'Cascadia Code', monospace",
            textAlign: "center",
            maxWidth: "80%",
            lineHeight: 1.4,
          }}
        >
          {ctaText}
        </div>
      )}
    </AbsoluteFill>
  );
};
