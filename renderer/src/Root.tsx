import {Composition, continueRender, delayRender, staticFile} from 'remotion';
import {useCallback, useEffect, useState} from 'react';
import {AvatarRetention} from './AvatarRetention';
import type {AvatarPlan} from './types';

const fallbackData: AvatarPlan = {
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

export const Root = () => {
  const [data, setData] = useState<AvatarPlan | null>(null);
  const [handle] = useState(() => delayRender('Loading avatar plan'));

  const load = useCallback(async () => {
    try {
      const response = await fetch(staticFile('avatar_plan.json'));
      if (!response.ok) {
        throw new Error(`Missing avatar_plan.json (${response.status})`);
      }
      const json = (await response.json()) as AvatarPlan;
      setData(json);
    } catch (error) {
      console.warn(error);
      setData(fallbackData);
    } finally {
      continueRender(handle);
    }
  }, [handle]);

  useEffect(() => {
    load();
  }, [load]);

  const resolved = data ?? fallbackData;
  const fps = resolved.fps || 30;
  const durationInFrames = Math.max(30, Math.ceil((resolved.duration || 30) * fps));

  return (
    <Composition
      id="AvatarTax"
      component={AvatarRetention}
      durationInFrames={durationInFrames}
      fps={fps}
      width={1920}
      height={1080}
      defaultProps={{data: resolved}}
    />
  );
};
