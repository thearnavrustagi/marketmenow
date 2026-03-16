import { loadFont, fontFamily } from "@remotion/google-fonts/SpaceGrotesk";

const { fontFamily: loaded } = loadFont("normal", {
  weights: ["700"],
});

export const GRADEASY_FONT = loaded ?? fontFamily;
