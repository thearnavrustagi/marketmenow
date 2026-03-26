import {
  AbsoluteFill,
} from "remotion";
import type { VisualProps } from "../schema";

const UpvoteIcon: React.FC<{ color?: string }> = ({ color = "#FF4500" }) => (
  <svg width="16" height="16" viewBox="0 0 20 20" fill={color}>
    <path d="M10 3l7 7h-4v7H7v-7H3l7-7z" />
  </svg>
);

const RedditCard: React.FC<{
  title: string;
  subreddit: string;
  username: string;
  paragraphText: string;
  upvotes: string;
  mode: string;
}> = ({
  title,
  subreddit,
  username,
  paragraphText,
  upvotes,
  mode,
}) => {

  return (
    <div
      style={{
        position: "absolute",
        top: 40,
        left: 28,
        right: 28,
        zIndex: 10,
      }}
    >
      <div
        style={{
          background: "#FFFFFF",
          borderRadius: 12,
          padding: "20px 22px",
          display: "flex",
          flexDirection: "column",
          gap: 12,
          boxShadow: "0 2px 12px rgba(0, 0, 0, 0.15)",
        }}
      >
        {/* Subreddit + username header */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: "50%",
              background: "#FF4500",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 12,
              fontWeight: 800,
              color: "#fff",
              flexShrink: 0,
            }}
          >
            r/
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div
              style={{
                color: "#1A1A1B",
                fontSize: 16,
                fontWeight: 700,
                fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
                lineHeight: 1.2,
              }}
            >
              {subreddit}
            </div>
            <div
              style={{
                color: "#787C7E",
                fontSize: 12,
                fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
              }}
            >
              Posted by {username}
            </div>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 4 }}>
            <UpvoteIcon />
            <span
              style={{
                color: "#FF4500",
                fontSize: 14,
                fontWeight: 700,
                fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
              }}
            >
              {upvotes}
            </span>
          </div>
        </div>

        {/* Divider */}
        <div style={{ height: 1, background: "#EDEFF1" }} />

        {/* Title */}
        <div
          style={{
            color: "#1A1A1B",
            fontSize: 30,
            fontWeight: 700,
            fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
            lineHeight: 1.3,
          }}
        >
          {title}
        </div>

        {/* Paragraph body */}
        {mode !== "title" && (
          <div
            style={{
              color: "#1A1A1B",
              fontSize: 26,
              fontWeight: 400,
              fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
              lineHeight: 1.5,
            }}
          >
            {paragraphText}
          </div>
        )}

        {/* Bottom bar */}
        <div style={{ display: "flex", alignItems: "center", gap: 18, paddingTop: 4 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <svg width="14" height="14" viewBox="0 0 20 20" fill="#878A8C">
              <path d="M18 10c0 3.87-3.58 7-8 7a9.1 9.1 0 01-3.46-.68L2 18l1.46-3.66A6.46 6.46 0 012 10c0-3.87 3.58-7 8-7s8 3.13 8 7z" />
            </svg>
            <span style={{ color: "#878A8C", fontSize: 12, fontWeight: 700, fontFamily: "'IBM Plex Sans', system-ui" }}>
              Comment
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <svg width="14" height="14" viewBox="0 0 20 20" fill="#878A8C">
              <path d="M10 18c-4.4 0-8-3.6-8-8s3.6-8 8-8 8 3.6 8 8-3.6 8-8 8zm-1-5h2v2H9v-2zm0-8h2v6H9V5z" />
            </svg>
            <span style={{ color: "#878A8C", fontSize: 12, fontWeight: 700, fontFamily: "'IBM Plex Sans', system-ui" }}>
              Share
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export const RedditStoryScene: React.FC<{ visual: VisualProps }> = ({ visual }) => {
  const title = (visual.title as string) ?? "";
  const subreddit = (visual.subreddit as string) ?? "r/nosleep";
  const username = (visual.username as string) ?? "u/anonymous";
  const paragraphText = (visual.paragraph_text as string) ?? "";
  const upvotes = (visual.upvotes as string) ?? "2.4k";
  const mode = (visual.mode as string) ?? "paragraph";
  return (
    <AbsoluteFill>
      {/* Reddit card — compact, light mode, top-aligned */}
      <RedditCard
        title={title}
        subreddit={subreddit}
        username={username}
        paragraphText={paragraphText}
        upvotes={upvotes}
        mode={mode}
      />
    </AbsoluteFill>
  );
};
