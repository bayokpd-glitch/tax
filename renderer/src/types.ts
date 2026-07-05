export type ZoomEvent = {
  start: number;
  end: number;
  fromScale?: number;
  fromX?: number;
  fromY?: number;
  scale: number;
  x: number;
  y: number;
  mode?: 'flash' | 'punch' | 'slow' | 'steady' | 'settle';
};

export type OverlayEvent = {
  kind:
    | 'title_card'
    | 'soft_caption'
    | 'underline_callout'
    | 'strike_callout'
    | 'mistake_strip'
    | 'form_highlight'
    | 'receipt_stack'
    | 'rule_slate'
    | 'mistake_teardown'
    | 'deadline_flip'
    | 'money_leak'
    | 'checklist_reveal'
    | 'document_scan'
    | 'stat_counter'
    | 'bar_chart'
    | 'donut_chart'
    | 'tax_card'
    | 'warning_card'
    | 'deadline_card'
    | 'money_card'
    | 'checklist_card';
  time: number;
  duration: number;
  text: string;
  value?: string;
  label?: string;
  items?: string[];
  data?: Array<{label: string; value: number}>;
  meter?: number;
  icon?: 'receipt' | 'warning' | 'calendar' | 'dollar' | 'check';
  tone?: 'money' | 'warning' | 'deadline' | 'audit' | 'neutral';
  number?: number;
  progressive?: boolean;
  accent?: 'yellow' | 'white' | 'green';
  sfx?: 'hit' | 'pop' | 'click' | 'whoosh';
};

export type ImageInsert = {
  time: number;
  duration: number;
  path: string;
  caption: string;
  source?: string;
};

export type AvatarPlan = {
  title: string;
  duration: number;
  fps: number;
  avatarVideo: string;
  sfx: Record<string, string>;
  chapters: Array<{
    number: number;
    start: number;
    end: number;
    title: string;
  }>;
  zooms: ZoomEvent[];
  overlays: OverlayEvent[];
  images: ImageInsert[];
};
