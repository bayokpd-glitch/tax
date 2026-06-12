export type ArchiveMode =
  | 'photo'
  | 'dossier'
  | 'map'
  | 'timeline'
  | 'memory'
  | 'number';

export type ArchiveScene = {
  index: number;
  text: string;
  prompt: string;
  image: string;
  start: number;
  end: number;
  mode: ArchiveMode;
  label: string;
  visualText: string;
  dateHint: string;
  motion: string;
  accent?: string;
  sfx?: string;
};

export type ArchiveCaption = {
  start: number;
  end: number;
  text: string;
};

export type ArchiveData = {
  title: string;
  fps: number;
  duration: number;
  audio: string;
  captions?: ArchiveCaption[];
  sfx?: {
    projectorStart?: string;
    cameraClick?: string;
    paperSlide?: string;
  };
  scenes: ArchiveScene[];
};
