import {
  AbsoluteFill,
  Img,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { VisualProps } from "../schema";
import { GRADEASY_FONT } from "../fonts";

const BRAND_BLUE = "#4A8DF8";
const FRAME_BG = "#E0E0E0";

export const RoastScene: React.FC<{ visual: VisualProps }> = ({ visual }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const rawImage = (visual.image as string) ?? "";
  const imageSrc = rawImage ? staticFile(rawImage) : "";

  const imageScale = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 80, mass: 0.8 },
  });

  const panelSlide = spring({
    frame: Math.max(0, frame - 6),
    fps,
    config: { damping: 16, stiffness: 100, mass: 0.7 },
  });

  return (
    <AbsoluteFill style={{ background: BRAND_BLUE }}>
      {/* Assignment image in gray frame */}
      {imageSrc && (
        <div
          style={{
            position: "absolute",
            top: "8%",
            left: "50%",
            transform: `translateX(-50%) scale(${imageScale})`,
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            width: "72%",
            height: "50%",
            background: FRAME_BG,
            borderRadius: 8,
            padding: 24,
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

      {/* Dark bottom panel — branding only, no text overlay */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: "38%",
          background: "#0A0A0A",
          borderTopLeftRadius: 40,
          borderTopRightRadius: 40,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          transform: `translateY(${200 * (1 - panelSlide)}px)`,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            fontFamily: GRADEASY_FONT,
          }}
        >
          <span
            style={{
              color: "#FFFFFF",
              fontSize: 64,
              fontWeight: 700,
              letterSpacing: -1,
            }}
          >
            Gradeasy
          </span>
          <span
            style={{
              color: BRAND_BLUE,
              fontSize: 64,
              fontWeight: 700,
              letterSpacing: -1,
            }}
          >
            .ai
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
