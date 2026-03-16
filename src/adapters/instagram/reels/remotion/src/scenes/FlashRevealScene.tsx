import {
  AbsoluteFill,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { VisualProps } from "../schema";

export const FlashRevealScene: React.FC<{ visual: VisualProps }> = ({
  visual,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const rawImage = (visual.image as string) ?? "";
  const imageSrc = rawImage ? staticFile(rawImage) : "";
  const flashColor = (visual.flash_color as string) ?? "#ffffff";
  const flashDur = Number(visual.flash_duration ?? 0.3);
  const flashFrames = Math.ceil(flashDur * fps);

  // Flash: starts fully opaque, fades out
  const flashOpacity = interpolate(frame, [0, flashFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Image: hidden during the peak of the flash, then fades in
  const imageAppearStart = Math.floor(flashFrames * 0.4);
  const imageOpacity = interpolate(
    frame,
    [imageAppearStart, flashFrames],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  // Subtle slow zoom on the held image
  const zoom = interpolate(frame, [flashFrames, fps * 5], [1, 1.08], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: "#000" }}>
      {/* Image underneath */}
      {imageSrc && (
        <AbsoluteFill
          style={{
            justifyContent: "center",
            alignItems: "center",
            opacity: imageOpacity,
          }}
        >
          <Img
            src={imageSrc}
            style={{
              maxWidth: "92%",
              maxHeight: "88%",
              objectFit: "contain",
              borderRadius: 12,
              transform: `scale(${zoom})`,
            }}
          />
        </AbsoluteFill>
      )}

      {/* Flash overlay */}
      <AbsoluteFill
        style={{
          background: flashColor,
          opacity: flashOpacity,
          zIndex: 10,
        }}
      />
    </AbsoluteFill>
  );
};
