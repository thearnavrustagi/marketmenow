import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { VisualProps } from "../schema";

interface RubricItem {
  name: string;
  description: string;
  max_points: number;
}

export const RubricScene: React.FC<{ visual: VisualProps }> = ({ visual }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  let rubricItems: RubricItem[] = [];
  const rawItems = visual.rubric_items;
  if (Array.isArray(rawItems)) {
    rubricItems = rawItems as RubricItem[];
  } else if (typeof rawItems === "string" && rawItems.trim()) {
    try {
      rubricItems = JSON.parse(rawItems);
    } catch {
      try {
        rubricItems = JSON.parse(rawItems.replace(/'/g, '"'));
      } catch {}
    }
  }

  const cardSpring = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 100 },
  });
  const cardScale = interpolate(cardSpring, [0, 1], [0.9, 1]);
  const cardOpacity = interpolate(cardSpring, [0, 1], [0, 1]);

  const staggerDelay = Math.floor(fps * 0.35);

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(135deg, #4285f4, #5c6bc0)",
        justifyContent: "center",
        alignItems: "center",
        padding: 36,
      }}
    >
      <div
        style={{
          opacity: cardOpacity,
          transform: `scale(${cardScale})`,
          background: "#fff",
          borderRadius: 28,
          padding: "40px 36px",
          width: "94%",
          maxHeight: "90%",
          boxShadow: "0 12px 40px rgba(0,0,0,0.2)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            fontSize: 48,
            fontWeight: 900,
            color: "#1a1a1a",
            fontFamily: "system-ui, sans-serif",
            marginBottom: 32,
          }}
        >
          Rubric
        </div>

        {/* Rubric items */}
        {rubricItems.map((item, idx) => {
          const entryFrame = (idx + 1) * staggerDelay;
          const itemSpring = spring({
            frame: Math.max(0, frame - entryFrame),
            fps,
            config: { damping: 12, stiffness: 100 },
          });
          const translateY = interpolate(itemSpring, [0, 1], [60, 0]);
          const opacity = interpolate(itemSpring, [0, 1], [0, 1]);

          return (
            <div
              key={item.name}
              style={{
                opacity,
                transform: `translateY(${translateY}px)`,
                background: "#f8f8f8",
                border: "1.5px solid #e0e0e0",
                borderRadius: 20,
                padding: "28px 30px",
                marginBottom: 20,
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 14,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                  <div
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: 10,
                      background: "#222",
                      color: "#fff",
                      display: "flex",
                      justifyContent: "center",
                      alignItems: "center",
                      fontSize: 22,
                      fontWeight: 800,
                      fontFamily: "system-ui, sans-serif",
                      flexShrink: 0,
                    }}
                  >
                    {idx + 1}
                  </div>
                  <span
                    style={{
                      fontSize: 32,
                      fontWeight: 800,
                      color: "#1a1a1a",
                      fontFamily: "system-ui, sans-serif",
                    }}
                  >
                    {item.name}
                  </span>
                </div>
                <span
                  style={{
                    fontSize: 32,
                    fontWeight: 700,
                    color: "#1a1a1a",
                    fontFamily: "system-ui, sans-serif",
                    flexShrink: 0,
                  }}
                >
                  {item.max_points}
                </span>
              </div>
              <div
                style={{
                  fontSize: 24,
                  color: "#555",
                  fontFamily: "system-ui, sans-serif",
                  lineHeight: 1.5,
                }}
              >
                {item.description}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
