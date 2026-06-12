export type Word = {
  word: string;
  start: number;
  end: number;
};

export type Scene = {
  type: "image" | "headline" | "quote" | "stat" | "timeline" | "fallback_card";
  start: number;
  end: number;
  text: string;
  headline: string;
  context_label?: string;
  image?: string;
  source?: string;
  query?: string;
  motion?: "zoom_in" | "zoom_out" | "pan_left" | "pan_right" | "drift_up";
  speaker?: string;
  quote?: string;
  stat_value?: string;
  stat_label?: string;
  timeline_items?: string[];
  aligned?: boolean;
};

export type ScenesData = {
  title: string;
  channel: string;
  audio: string;
  background?: string;
  background_duration?: number | null;
  duration: number;
  fps?: number;
  scenes: Scene[];
  ending?: {
    kind?: "next" | "subscribe";
    headline: string;
    text: string;
  };
  words?: Word[];
};
