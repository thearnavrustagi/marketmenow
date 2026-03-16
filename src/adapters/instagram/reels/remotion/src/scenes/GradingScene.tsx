import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { VisualProps } from "../schema";

interface RubricEval {
  rubric_item_name: string;
  points_awarded: number;
  max_points: number;
  feedback: string;
}

interface GradingResultData {
  points_awarded?: number;
  max_points?: number;
  rubric_evaluations?: RubricEval[];
}

function scoreRatio(awarded: number, max: number): number {
  return max > 0 ? awarded / max : 0;
}

function scoreLabel(ratio: number): string {
  if (ratio >= 0.9) return "Excellent";
  if (ratio >= 0.7) return "Good";
  if (ratio >= 0.5) return "Fair";
  return "Needs Work";
}

function colorsForRatio(ratio: number) {
  if (ratio >= 0.7)
    return { accent: "#2d6a4f", bg: "#e6f4ed", bar: "#34a853" };
  if (ratio >= 0.4)
    return { accent: "#7f4f24", bg: "#fef7e6", bar: "#f9ab00" };
  return { accent: "#9d0208", bg: "#fde8e8", bar: "#ea4335" };
}

function overallColorsForRatio(ratio: number) {
  if (ratio >= 0.7) return { accent: "#2d6a4f" };
  if (ratio >= 0.5) return { accent: "#7f4f24" };
  return { accent: "#9d0208" };
}

export const GradingScene: React.FC<{ visual: VisualProps }> = ({ visual }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  let evaluations: RubricEval[] = [];
  let totalAwarded = 0;
  let totalMax = 0;
  const rawResult = visual.grading_result;
  let parsedResult: GradingResultData | null = null;
  if (rawResult && typeof rawResult === "object") {
    parsedResult = rawResult as GradingResultData;
  } else if (typeof rawResult === "string" && rawResult.trim()) {
    try {
      parsedResult = JSON.parse(rawResult) as GradingResultData;
    } catch {
      try {
        parsedResult = JSON.parse(
          rawResult.replace(/'/g, '"'),
        ) as GradingResultData;
      } catch {}
    }
  }
  if (parsedResult) {
    evaluations = parsedResult.rubric_evaluations ?? [];
    totalAwarded = parsedResult.points_awarded ?? 0;
    totalMax = parsedResult.max_points ?? 0;
  }

  const fmtScore = (n: number) =>
    Number.isInteger(n) ? String(n) : n.toFixed(0);

  const overallRatio = scoreRatio(totalAwarded, totalMax);
  const overall = overallColorsForRatio(overallRatio);

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
          maxHeight: "92%",
          boxShadow: "0 12px 40px rgba(0,0,0,0.2)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            marginBottom: 28,
            paddingBottom: 24,
            borderBottom: "2px solid #f0ece7",
          }}
        >
          <div>
            <div
              style={{
                fontSize: 18,
                fontWeight: 600,
                color: "#999",
                fontFamily: "'DM Sans', system-ui, sans-serif",
                textTransform: "uppercase",
                letterSpacing: 4,
                marginBottom: 8,
              }}
            >
              Evaluation
            </div>
            <div
              style={{
                fontSize: 48,
                fontWeight: 900,
                color: "#1a1a1a",
                fontFamily: "system-ui, sans-serif",
              }}
            >
              Rubric Breakdown
            </div>
          </div>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "flex-end",
              gap: 4,
            }}
          >
            <div
              style={{
                fontSize: 52,
                fontWeight: 900,
                color: overall.accent,
                fontFamily: "'Space Grotesk', system-ui, sans-serif",
                lineHeight: 1,
              }}
            >
              {fmtScore(totalAwarded)}/{fmtScore(totalMax)}
            </div>
            <div
              style={{
                fontSize: 18,
                fontWeight: 700,
                color: overall.accent,
                fontFamily: "'DM Sans', system-ui, sans-serif",
                textTransform: "uppercase",
                letterSpacing: 2,
              }}
            >
              {scoreLabel(overallRatio)}
            </div>
          </div>
        </div>

        {/* Evaluation cards */}
        {evaluations.map((ev, idx) => {
          const entryFrame = (idx + 1) * staggerDelay;
          const itemSpring = spring({
            frame: Math.max(0, frame - entryFrame),
            fps,
            config: { damping: 12, stiffness: 100 },
          });
          const translateY = interpolate(itemSpring, [0, 1], [60, 0]);
          const opacity = interpolate(itemSpring, [0, 1], [0, 1]);

          const ratio = scoreRatio(ev.points_awarded, ev.max_points);
          const colors = colorsForRatio(ratio);
          const pctFilled = Math.round(ratio * 100);

          return (
            <div
              key={ev.rubric_item_name}
              style={{
                opacity,
                transform: `translateY(${translateY}px)`,
                background: colors.bg,
                border: `1.5px solid ${colors.bar}30`,
                borderRadius: 20,
                padding: "24px 28px",
                marginBottom: 18,
                position: "relative",
                overflow: "hidden",
              }}
            >
              {/* Left color bar */}
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  top: 0,
                  bottom: 0,
                  width: 5,
                  background: colors.bar,
                  borderRadius: "20px 0 0 20px",
                }}
              />

              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 12,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                  <div
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: 10,
                      background: colors.bar,
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
                      fontSize: 30,
                      fontWeight: 800,
                      color: "#1a1a1a",
                      fontFamily: "system-ui, sans-serif",
                    }}
                  >
                    {ev.rubric_item_name}
                  </span>
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    flexShrink: 0,
                  }}
                >
                  {/* Mini progress bar */}
                  <div
                    style={{
                      width: 80,
                      height: 10,
                      background: `${colors.bar}25`,
                      borderRadius: 5,
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        width: `${pctFilled}%`,
                        height: "100%",
                        background: colors.bar,
                        borderRadius: 5,
                      }}
                    />
                  </div>
                  <span
                    style={{
                      fontSize: 28,
                      fontWeight: 800,
                      color: colors.accent,
                      fontFamily: "'Space Grotesk', system-ui, sans-serif",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {ev.points_awarded}/{ev.max_points}
                  </span>
                </div>
              </div>
              <div
                style={{
                  fontSize: 22,
                  color: "#555",
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  lineHeight: 1.5,
                  paddingLeft: 60,
                }}
              >
                {ev.feedback}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
