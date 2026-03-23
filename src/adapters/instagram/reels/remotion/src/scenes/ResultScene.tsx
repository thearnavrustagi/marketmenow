import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { VisualProps } from "../schema";

function gradeColors(pct: number) {
  if (pct >= 0.9)
    return { accent: "#2d6a4f", bg: "#d8f3dc", ring: "#95d5b2", label: "Excellent" };
  if (pct >= 0.7)
    return { accent: "#3d5a80", bg: "#e0ecf4", ring: "#89c2d9", label: "Good" };
  if (pct >= 0.5)
    return { accent: "#7f4f24", bg: "#fefae0", ring: "#dda15e", label: "Fair" };
  return { accent: "#9d0208", bg: "#fde8e8", ring: "#e5383b", label: "Needs Work" };
}

export const ResultScene: React.FC<{ visual: VisualProps }> = ({ visual }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const rawGrade = (visual.grade as string) ?? "?/?";
  const feedback = (visual.feedback as string) ?? "";

  const parts = rawGrade.split("/");
  const awarded = parseFloat(parts[0] ?? "0");
  const max = parseFloat(parts[1] ?? "100");
  const pct = max > 0 ? awarded / max : 0;

  const fmtNum = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(0));
  const grade = `${fmtNum(awarded)}/${fmtNum(max)}`;

  const colors = gradeColors(pct);

  const cardSpring = spring({
    frame,
    fps,
    config: { damping: 12, stiffness: 120 },
  });
  const cardScale = interpolate(cardSpring, [0, 1], [0.85, 1]);
  const cardOpacity = interpolate(cardSpring, [0, 1], [0, 1]);

  const gradeSpring = spring({
    frame: Math.max(0, frame - Math.floor(fps * 0.15)),
    fps,
    config: { damping: 8, stiffness: 200, mass: 0.8 },
  });
  const gradeScale = interpolate(gradeSpring, [0, 1], [0.3, 1]);
  const gradeOpacity = interpolate(gradeSpring, [0, 1], [0, 1]);

  const feedbackDelay = Math.floor(fps * 0.5);
  const feedbackSpring = spring({
    frame: Math.max(0, frame - feedbackDelay),
    fps,
    config: { damping: 14, stiffness: 80 },
  });
  const feedbackOpacity = interpolate(feedbackSpring, [0, 1], [0, 1]);
  const feedbackY = interpolate(feedbackSpring, [0, 1], [24, 0]);

  const ringProgress = interpolate(
    spring({
      frame: Math.max(0, frame - Math.floor(fps * 0.2)),
      fps,
      config: { damping: 20, stiffness: 60 },
    }),
    [0, 1],
    [0, pct],
  );

  const ringSize = Number(visual.ring_size ?? 380);
  const ringRadius = ringSize * (155 / 380);
  const circumference = 2 * Math.PI * ringRadius;
  const strokeDashoffset = circumference * (1 - ringProgress);

  return (
    <AbsoluteFill
      style={{
        background: (visual.background as string) ?? "#faf8f5",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      {/* Decorative top-left blob */}
      <div
        style={{
          position: "absolute",
          top: -80,
          left: -80,
          width: 320,
          height: 320,
          borderRadius: "50%",
          background: `${colors.ring}22`,
        }}
      />
      {/* Decorative bottom-right blob */}
      <div
        style={{
          position: "absolute",
          bottom: -60,
          right: -60,
          width: 240,
          height: 240,
          borderRadius: "50%",
          background: `${colors.ring}18`,
        }}
      />

      <div
        style={{
          opacity: cardOpacity,
          transform: `scale(${cardScale})`,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          width: "88%",
          maxWidth: 900,
        }}
      >
        {/* Label */}
        <div
          style={{
            fontSize: Number(visual.header_font_size ?? 22),
            fontWeight: 600,
            color: "#aaa",
            fontFamily: "'DM Sans', system-ui, sans-serif",
            textTransform: "uppercase",
            letterSpacing: 6,
            marginBottom: 44,
          }}
        >
          Final Result
        </div>

        {/* Circular ring + grade */}
        <div
          style={{
            position: "relative",
            width: ringSize,
            height: ringSize,
            marginBottom: 36,
            opacity: gradeOpacity,
            transform: `scale(${gradeScale})`,
          }}
        >
          <svg
            viewBox={`0 0 ${ringSize} ${ringSize}`}
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: ringSize,
              height: ringSize,
              transform: "rotate(-90deg)",
            }}
          >
            <circle
              cx={ringSize / 2}
              cy={ringSize / 2}
              r={ringRadius}
              fill="none"
              stroke="#f0ece7"
              strokeWidth="14"
            />
            <circle
              cx={ringSize / 2}
              cy={ringSize / 2}
              r={ringRadius}
              fill="none"
              stroke={colors.accent}
              strokeWidth="14"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
            />
          </svg>
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              alignItems: "center",
            }}
          >
            <div
              style={{
                fontSize: Number(visual.grade_font_size ?? 64),
                fontWeight: 900,
                color: colors.accent,
                fontFamily: "'Space Grotesk', system-ui, sans-serif",
                lineHeight: 1,
              }}
            >
              {grade}
            </div>
          </div>
        </div>

        {/* Score label */}
        <div
          style={{
            opacity: gradeOpacity,
            fontSize: Number(visual.label_font_size ?? 36),
            fontWeight: 800,
            color: colors.accent,
            fontFamily: "'Space Grotesk', system-ui, sans-serif",
            textTransform: "uppercase",
            letterSpacing: 5,
            marginBottom: 44,
          }}
        >
          {colors.label}
        </div>

        {/* Divider */}
        <div
          style={{
            width: 60,
            height: 3,
            background: colors.ring,
            borderRadius: 2,
            marginBottom: 40,
          }}
        />

        {/* Feedback */}
        <div
          style={{
            opacity: feedbackOpacity,
            transform: `translateY(${feedbackY}px)`,
            background: "#ffffff",
            borderRadius: Number(visual.card_border_radius ?? 20),
            padding: "36px 40px",
            boxShadow: "0 2px 16px rgba(0,0,0,0.05)",
            border: "1px solid #ebe7e2",
            width: "100%",
          }}
        >
          <div
            style={{
              color: "#444",
              fontSize: Number(visual.feedback_font_size ?? 32),
              fontWeight: 500,
              fontFamily: "'DM Sans', system-ui, sans-serif",
              textAlign: "center",
              lineHeight: 1.55,
            }}
          >
            {feedback}
          </div>
        </div>

        {/* Bottom brand */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginTop: 32,
          }}
        >
          <div style={{ width: 40, height: 2, background: "#d0ccc6" }} />
          <span
            style={{
              fontSize: 16,
              fontWeight: 600,
              color: "#bbb",
              fontFamily: "'DM Sans', system-ui, sans-serif",
              letterSpacing: 2,
              textTransform: "uppercase",
            }}
          >
            {(visual.brand_name as string) ?? "BrandName"}
          </span>
          <div style={{ width: 40, height: 2, background: "#d0ccc6" }} />
        </div>
      </div>
    </AbsoluteFill>
  );
};
