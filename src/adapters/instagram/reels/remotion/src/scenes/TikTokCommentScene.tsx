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

export const TikTokCommentScene: React.FC<{ visual: VisualProps }> = ({
  visual,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const username = (visual.username as string) ?? "user";
  const avatarRaw = (visual.avatar as string) ?? "";
  const avatarSrc = avatarRaw ? staticFile(avatarRaw) : "";
  const commentText = (visual.comment_text as string) ?? "";
  const showImage = visual.show_image === true || visual.show_image === "true";
  const commentImageRaw = (visual.comment_image as string) ?? "";
  const commentImageSrc =
    showImage && commentImageRaw ? staticFile(commentImageRaw) : "";

  const cardSlide = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 120 },
  });
  const translateY = interpolate(cardSlide, [0, 1], [300, 0]);
  const cardOpacity = interpolate(frame, [0, fps * 0.15], [0, 1], {
    extrapolateRight: "clamp",
  });

  const imageSlide = spring({
    frame,
    fps,
    config: { damping: 12, stiffness: 100 },
  });
  const imageOpacity = interpolate(frame, [0, fps * 0.25], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: "#000",
        justifyContent: "center",
        alignItems: "center",
        padding: 40,
      }}
    >
      <div
        style={{
          opacity: cardOpacity,
          transform: `translateY(${translateY}px)`,
          background: "#fff",
          borderRadius: 16,
          width: "90%",
          maxWidth: 900,
          overflow: "hidden",
          boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 16,
            padding: "24px 28px 16px",
          }}
        >
          {avatarSrc ? (
            <Img
              src={avatarSrc}
              style={{
                width: 56,
                height: 56,
                borderRadius: "50%",
                objectFit: "cover",
                flexShrink: 0,
              }}
            />
          ) : (
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: "50%",
                background: "linear-gradient(135deg, #667eea, #764ba2)",
                flexShrink: 0,
              }}
            />
          )}
          <div style={{ flex: 1 }}>
            <div
              style={{
                fontSize: 22,
                fontWeight: 700,
                color: "#1a1a1a",
                fontFamily: "system-ui, sans-serif",
                marginBottom: 4,
              }}
            >
              {username}
            </div>
            <div
              style={{
                fontSize: 28,
                fontWeight: 400,
                color: "#262626",
                fontFamily: "system-ui, sans-serif",
                lineHeight: 1.4,
              }}
            >
              {commentText}
            </div>
          </div>
        </div>

        {commentImageSrc && (
          <div
            style={{
              padding: "0 28px 24px",
              opacity: imageOpacity,
              transform: `scale(${interpolate(imageSlide, [0, 1], [0.9, 1])})`,
            }}
          >
            <Img
              src={commentImageSrc}
              style={{
                width: "100%",
                maxHeight: 800,
                objectFit: "contain",
                borderRadius: 12,
                background: "#f5f5f5",
              }}
            />
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};
