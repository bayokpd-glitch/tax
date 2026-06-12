import {Composition, continueRender, delayRender, staticFile} from 'remotion';
import {useCallback, useEffect, useState} from 'react';
import {AvatarRetention} from './AvatarRetention';
import {MainComposition} from './news/MainComposition';
import {ArchiveDocumentary} from './archive/ArchiveDocumentary';
import type {AvatarPlan} from './types';
import type {ScenesData} from './news/types';
import type {ArchiveData} from './archive/types';

const fallbackAvatar: AvatarPlan = {
  title: 'Avatar Tax',
  duration: 30,
  fps: 30,
  avatarVideo: '',
  sfx: {},
  chapters: [],
  zooms: [],
  overlays: [
    {
      kind: 'title_card',
      time: 0,
      duration: 2.6,
      text: 'Build a project from the Python app',
      number: 1,
      accent: 'yellow',
      sfx: 'hit',
    },
  ],
  images: [],
};

const fallbackNews: ScenesData = {
  title: 'Flash Report',
  channel: 'Flash Report',
  audio: '',
  duration: 8,
  fps: 30,
  scenes: [
    {
      type: 'headline',
      start: 0,
      end: 8,
      text: 'Build a package from Flash News Factory.',
      headline: 'Flash Report',
    },
  ],
};

const fallbackArchive: ArchiveData = {
  title: 'Archive Documentary',
  fps: 30,
  duration: 8,
  audio: '',
  scenes: [],
};

async function readJsonOrFallback<T>(file: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(staticFile(file));
    if (!response.ok) {
      throw new Error(`Missing ${file} (${response.status})`);
    }
    return (await response.json()) as T;
  } catch (error) {
    console.warn(error);
    return fallback;
  }
}

export const Root = () => {
  const [avatar, setAvatar] = useState<AvatarPlan | null>(null);
  const [news, setNews] = useState<ScenesData | null>(null);
  const [archive, setArchive] = useState<ArchiveData | null>(null);
  const [handle] = useState(() => delayRender('Loading render package data'));

  const load = useCallback(async () => {
    try {
      const [avatarData, newsData, archiveData] = await Promise.all([
        readJsonOrFallback('avatar_plan.json', fallbackAvatar),
        readJsonOrFallback('scenes.json', fallbackNews),
        readJsonOrFallback('archive.json', fallbackArchive),
      ]);
      setAvatar(avatarData);
      setNews(newsData);
      setArchive(archiveData);
    } finally {
      continueRender(handle);
    }
  }, [handle]);

  useEffect(() => {
    load();
  }, [load]);

  const avatarData = avatar ?? fallbackAvatar;
  const newsData = news ?? fallbackNews;
  const archiveData = archive ?? fallbackArchive;
  const avatarFps = avatarData.fps || 30;
  const newsFps = newsData.fps || 30;
  const archiveFps = archiveData.fps || 30;

  return (
    <>
      <Composition
        id="AvatarTax"
        component={AvatarRetention}
        durationInFrames={Math.max(30, Math.ceil((avatarData.duration || 30) * avatarFps))}
        fps={avatarFps}
        width={1920}
        height={1080}
        defaultProps={{data: avatarData}}
      />
      <Composition
        id="NewsFlash"
        component={MainComposition}
        durationInFrames={Math.max(30, Math.ceil((newsData.duration || 8) * newsFps))}
        fps={newsFps}
        width={1920}
        height={1080}
        defaultProps={{data: newsData}}
      />
      <Composition
        id="ArchiveDocumentary"
        component={ArchiveDocumentary}
        durationInFrames={Math.max(30, Math.ceil((archiveData.duration || 8) * archiveFps))}
        fps={archiveFps}
        width={1920}
        height={1080}
        defaultProps={{data: archiveData}}
      />
    </>
  );
};
