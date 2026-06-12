import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  Loop,
  OffthreadVideo,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type {Scene, ScenesData} from "./types";

type Props = {
  data: ScenesData;
};

const bg = "#070B12";
const panel = "#0D1420";
const panelSoft = "rgba(13, 20, 32, 0.86)";
const red = "#E63232";
const blue = "#2F7DF6";
const text = "#F5F7FA";
const muted = "#9AA4B2";
const line = "rgba(255,255,255,0.12)";

function useSceneTime(scene: Scene) {
  const {fps} = useVideoConfig();
  const from = Math.max(0, Math.round(scene.start * fps));
  const durationInFrames = Math.max(1, Math.round((scene.end - scene.start) * fps));
  return {from, durationInFrames};
}

function SceneTransition({
  durationInFrames,
  children,
}: {
  durationInFrames: number;
  children: React.ReactNode;
}) {
  const frame = useCurrentFrame();
  const fadeFrames = Math.min(14, Math.max(6, Math.floor(durationInFrames / 3)));
  const fadeIn = interpolate(frame, [0, fadeFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(frame, [durationInFrames - fadeFrames, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return <AbsoluteFill style={{opacity: Math.min(fadeIn, fadeOut)}}>{children}</AbsoluteFill>;
}

const FrameChrome: React.FC<{data: ScenesData}> = ({data}) => {
  return (
    <AbsoluteFill style={{pointerEvents: "none"}}>
      <div
        style={{
          position: "absolute",
          top: 42,
          left: 54,
          display: "flex",
          alignItems: "center",
          gap: 18,
          color: "white",
          fontFamily: "Arial, Helvetica, sans-serif",
          fontWeight: 800,
          letterSpacing: 0,
          textTransform: "uppercase",
        }}
      >
        <div style={{width: 14, height: 14, background: red}} />
        <div style={{fontSize: 26}}>{data.channel}</div>
      </div>
      <div
        style={{
          position: "absolute",
          right: 54,
          bottom: 40,
          color: "rgba(255,255,255,0.78)",
          fontFamily: "Arial, Helvetica, sans-serif",
          fontSize: 22,
          letterSpacing: 0,
          textTransform: "uppercase",
        }}
      >
        Flash Report
      </div>
    </AbsoluteFill>
  );
};

const ImageScene: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const isOpening = scene.start < 0.25;
  const progress = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const scale = scene.motion === "zoom_out" ? 1.1 - progress * 0.06 : 1.02 + progress * 0.08;
  const panX =
    scene.motion === "pan_left" ? interpolate(progress, [0, 1], [22, -22]) :
    scene.motion === "pan_right" ? interpolate(progress, [0, 1], [-22, 22]) :
    0;
  const panY = scene.motion === "drift_up" ? interpolate(progress, [0, 1], [18, -18]) : 0;
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          inset: 0,
          overflow: "hidden",
          background: "#111",
        }}
      >
        {scene.image && (
          <Img
            src={staticFile(scene.image)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              transform: `translate(${panX}px, ${panY}px) scale(${scale})`,
            }}
          />
        )}
      </div>
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(90deg, rgba(7,11,18,0.62) 0%, rgba(7,11,18,0.16) 45%, rgba(7,11,18,0.34) 100%), linear-gradient(0deg, rgba(7,11,18,0.76) 0%, transparent 42%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 76,
          bottom: 74,
          width: isOpening ? 1320 : 1120,
          padding: isOpening ? "34px 40px" : "26px 32px",
          background: panelSoft,
          borderLeft: `7px solid ${red}`,
          borderTop: `1px solid ${line}`,
          color: "white",
          fontFamily: "Arial, Helvetica, sans-serif",
          boxShadow: "0 24px 70px rgba(0,0,0,0.42)",
        }}
      >
        <div
          style={{
            marginBottom: 12,
            color: red,
            fontSize: 20,
            lineHeight: 1,
            fontWeight: 900,
            letterSpacing: 0,
            textTransform: "uppercase",
          }}
        >
          {isOpening ? "The Latest" : scene.context_label || "Developing"}
        </div>
        <div style={{fontSize: isOpening ? 66 : 50, lineHeight: 1.04, fontWeight: 900}}>{scene.headline}</div>
        {scene.source && (
          <div style={{marginTop: 14, fontSize: 18, color: muted, textTransform: "uppercase"}}>
            Source image: {scene.source}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};

const HeadlineScene: React.FC<{scene: Scene}> = ({scene}) => (
  <AbsoluteFill
    style={{
      background:
        "radial-gradient(circle at 18% 24%, rgba(47,125,246,0.16), transparent 34%), linear-gradient(135deg, #070B12 0%, #0D1420 100%)",
      color: text,
      display: "flex",
      justifyContent: "center",
      padding: "0 150px",
      fontFamily: "Arial, Helvetica, sans-serif",
    }}
  >
    <div
      style={{
        maxWidth: 1460,
        borderLeft: `8px solid ${red}`,
        paddingLeft: 48,
      }}
    >
      <div style={{fontSize: 24, letterSpacing: 0, color: red, fontWeight: 900, textTransform: "uppercase", marginBottom: 28}}>
        Developing
      </div>
      <div style={{fontSize: 96, lineHeight: 1.03, fontWeight: 900, letterSpacing: 0}}>{scene.headline}</div>
      <div style={{marginTop: 32, fontSize: 34, lineHeight: 1.34, color: muted, maxWidth: 1260, fontWeight: 600}}>
        {scene.text}
      </div>
    </div>
  </AbsoluteFill>
);

const FallbackCard: React.FC<{scene: Scene}> = ({scene}) => (
  <AbsoluteFill
    style={{
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "0 150px",
      color: text,
      fontFamily: "Arial, Helvetica, sans-serif",
      background:
        "radial-gradient(circle at 80% 20%, rgba(230,50,50,0.12), transparent 30%), linear-gradient(135deg, #070B12 0%, #0B111B 100%)",
    }}
  >
    <div
      style={{
        width: "100%",
        padding: "62px 70px",
        background: panelSoft,
        borderLeft: `8px solid ${red}`,
        borderTop: `1px solid ${line}`,
        boxShadow: "0 42px 120px rgba(0,0,0,0.46)",
      }}
    >
      <div style={{fontSize: 24, letterSpacing: 0, color: red, fontWeight: 900, textTransform: "uppercase", marginBottom: 24}}>
        Context
      </div>
      <div style={{fontSize: 76, lineHeight: 1.04, fontWeight: 900}}>{scene.headline}</div>
      <div style={{marginTop: 28, fontSize: 34, lineHeight: 1.35, color: muted, fontWeight: 600}}>
        {scene.text}
      </div>
    </div>
  </AbsoluteFill>
);

const QuoteScene: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const quote = scene.quote || scene.text;
  const words = quote.split(/\s+/).filter(Boolean);
  const underline = interpolate(frame, [10, 42], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const speakerOpacity = interpolate(frame, [42, 62], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const driftA = Math.sin(frame * 0.018) * 12;
  const driftB = Math.sin(frame * 0.015 + 1.4) * 10;
  const scale = 1 + Math.sin(frame * 0.025) * 0.006;

  return (
    <AbsoluteFill
      style={{
        background: "#090b10",
        color: "white",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "0 220px",
        fontFamily: "Georgia, Times New Roman, serif",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 18,
          left: 90,
          color: red,
          fontSize: 470,
          lineHeight: 0.8,
          opacity: 0.13,
          transform: `translateY(${driftA}px)`,
        }}
      >
        “
      </div>
      <div
        style={{
          position: "absolute",
          right: 110,
          bottom: -28,
          color: red,
          fontSize: 360,
          lineHeight: 0.8,
          opacity: 0.1,
          transform: `translateY(${driftB}px)`,
        }}
      >
        ”
      </div>
      <div style={{maxWidth: 1430, textAlign: "center", transform: `scale(${scale})`}}>
        <div style={{fontSize: 96, lineHeight: 1.16, fontWeight: 700}}>
          {words.map((word, i) => {
            const start = i * 2.2;
            const opacity = interpolate(frame, [start, start + 10], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            const y = interpolate(frame, [start, start + 10], [18, 0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            return (
              <span
                key={`${word}-${i}`}
                style={{
                  display: "inline-block",
                  margin: "0 0.12em",
                  opacity,
                  transform: `translateY(${y}px)`,
                }}
              >
                {word}
              </span>
            );
          })}
        </div>
        <div
          style={{
            width: `${Math.round(underline * 76)}%`,
            height: 6,
            margin: "44px auto 0",
            background: red,
            boxShadow: "0 0 34px rgba(230,50,50,0.45)",
          }}
        />
        {scene.speaker && (
          <div
            style={{
              marginTop: 34,
              opacity: speakerOpacity,
              color: "#e8e8e8",
              fontFamily: "Arial, Helvetica, sans-serif",
              fontSize: 38,
              fontWeight: 800,
              letterSpacing: 0,
              textTransform: "uppercase",
            }}
          >
            {scene.speaker}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};

const StatScene: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const match = String(scene.stat_value || "").match(/^([^0-9-]*)(-?[0-9,.]+)(.*)$/);
  let value = scene.stat_value || scene.headline;
  if (match) {
    const n = Number(match[2].replace(/,/g, ""));
    if (!Number.isNaN(n)) {
      const p = interpolate(frame, [0, 38], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
      value = `${match[1]}${Math.round(n * p).toLocaleString("en-US")}${match[3]}`;
    }
  }
  const pulse = 1 + Math.sin(frame * 0.07) * 0.012;
  const sweep = interpolate(frame % 90, [0, 90], [-18, 118], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const progress = interpolate(frame, [0, Math.max(1, durationInFrames - 20)], [8, 100], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: "#0b1018",
        color: "white",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "column",
        fontFamily: "Arial, Helvetica, sans-serif",
        padding: 120,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px), linear-gradient(0deg, rgba(255,255,255,0.028) 1px, transparent 1px)",
          backgroundSize: "80px 80px",
          opacity: 0.38,
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 760,
          height: 760,
          borderRadius: 380,
          border: `2px solid ${red}`,
          opacity: 0.08 + Math.abs(Math.sin(frame * 0.04)) * 0.08,
          transform: `scale(${1 + Math.sin(frame * 0.035) * 0.05})`,
        }}
      />
      <div style={{fontSize: 32, letterSpacing: 0, textTransform: "uppercase", color: red, marginBottom: 34}}>
        {scene.stat_label || scene.headline}
      </div>
      <div
        style={{
          fontSize: 230,
          lineHeight: 0.95,
          fontWeight: 900,
          fontVariantNumeric: "tabular-nums",
          transform: `scale(${pulse})`,
          zIndex: 1,
        }}
      >
        {value}
      </div>
      <div
        style={{
          marginTop: 42,
          width: 640,
          height: 8,
          background: "rgba(255,255,255,0.12)",
          overflow: "hidden",
          position: "relative",
          zIndex: 1,
        }}
      >
        <div style={{width: `${progress}%`, height: "100%", background: blue}} />
        <div
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            left: `${sweep}%`,
            width: "18%",
            background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.7), transparent)",
          }}
        />
      </div>
      <div
        style={{
          marginTop: 34,
          maxWidth: 1180,
          fontSize: 30,
          lineHeight: 1.35,
          color: "rgba(255,255,255,0.68)",
          textAlign: "center",
          zIndex: 1,
        }}
      >
        {scene.text}
      </div>
    </AbsoluteFill>
  );
};

const TimelineScene: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const items = scene.timeline_items?.length ? scene.timeline_items : [scene.text];
  return (
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(circle at 16% 20%, rgba(47,125,246,0.14), transparent 34%), linear-gradient(135deg, #070B12 0%, #0D1420 100%)",
        color: text,
        fontFamily: "Arial, Helvetica, sans-serif",
        padding: "118px 150px",
      }}
    >
      <div style={{display: "flex", alignItems: "center", gap: 18, marginBottom: 28}}>
        <div style={{width: 16, height: 16, background: red}} />
        <div style={{fontSize: 24, color: red, fontWeight: 900, textTransform: "uppercase"}}>
          Timeline
        </div>
      </div>
      <div style={{fontSize: 72, lineHeight: 1.04, fontWeight: 900, marginBottom: 58, maxWidth: 1420}}>
        {scene.headline}
      </div>
      <div style={{display: "flex", flexDirection: "column", gap: 24, position: "relative"}}>
        <div
          style={{
            position: "absolute",
            left: 29,
            top: 28,
            bottom: 28,
            width: 4,
            background: `linear-gradient(${blue}, ${red})`,
            opacity: 0.55,
            transformOrigin: "top",
            transform: `scaleY(${interpolate(frame, [6, 44], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            })})`,
          }}
        />
        {items.map((item, i) => {
          const start = 8 + i * 12;
          const opacity = interpolate(frame, [start, start + 10], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          const x = interpolate(frame, [start, start + 10], [28, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          return (
            <div key={i} style={{display: "flex", alignItems: "center", gap: 32, opacity, transform: `translateX(${x}px)`}}>
              <div
                style={{
                  width: 58,
                  height: 58,
                  borderRadius: 29,
                  background: i === 0 ? red : blue,
                  color: "white",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 28,
                  fontWeight: 800,
                  flex: "0 0 auto",
                }}
              >
                {i + 1}
              </div>
              <div
                style={{
                  flex: 1,
                  minHeight: 76,
                  display: "flex",
                  alignItems: "center",
                  padding: "18px 26px",
                  background: panelSoft,
                  borderTop: `1px solid ${line}`,
                  borderRight: `1px solid ${line}`,
                  boxShadow: "0 22px 58px rgba(0,0,0,0.28)",
                  fontSize: 38,
                  lineHeight: 1.18,
                  fontWeight: 800,
                }}
              >
                {item}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const RenderScene: React.FC<{scene: Scene}> = ({scene}) => {
  let content: React.ReactNode;
  if (scene.type === "image" && scene.image) content = <ImageScene scene={scene} />;
  else if (scene.type === "headline") content = <HeadlineScene scene={scene} />;
  else if (scene.type === "quote") content = <QuoteScene scene={scene} />;
  else if (scene.type === "stat") content = <StatScene scene={scene} />;
  else if (scene.type === "timeline") content = <TimelineScene scene={scene} />;
  else content = <FallbackCard scene={scene} />;

  return (
    <AbsoluteFill>
      {content}
    </AbsoluteFill>
  );
};

const EndingCard: React.FC<{data: ScenesData}> = ({data}) => {
  const isSubscribe = data.ending?.kind === "subscribe";
  return (
    <AbsoluteFill
      style={{
        background: isSubscribe ? "#070b12" : "#060a10",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "white",
        fontFamily: "Arial, Helvetica, sans-serif",
        padding: "0 180px",
      }}
    >
      {isSubscribe && (
        <>
          <div
            style={{
              position: "absolute",
              width: 620,
              height: 620,
              borderRadius: 310,
              border: `2px solid ${red}`,
              opacity: 0.13,
              right: 160,
              top: 210,
            }}
          />
          <div
            style={{
              position: "absolute",
              right: 250,
              top: 310,
              width: 230,
              height: 230,
              borderRadius: 115,
              background: red,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "white",
              fontSize: 96,
              fontWeight: 900,
              boxShadow: "0 30px 80px rgba(230,50,50,0.35)",
            }}
          >
            +
          </div>
        </>
      )}
      <div
        style={{
          width: "100%",
          borderTop: `8px solid ${red}`,
          paddingTop: 44,
        }}
      >
        <div style={{fontSize: 30, letterSpacing: 0, color: red, fontWeight: 900, textTransform: "uppercase"}}>
          {data.ending?.headline || "What Happens Next"}
        </div>
        <div style={{marginTop: 24, fontSize: isSubscribe ? 108 : 86, lineHeight: 1.02, fontWeight: 900, maxWidth: 1260}}>
          {data.ending?.text || data.title}
        </div>
        {isSubscribe && (
          <div style={{marginTop: 34, fontSize: 34, color: "rgba(255,255,255,0.72)", maxWidth: 1050, lineHeight: 1.35}}>
            Subscribe for concise updates as the story develops.
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};

export const MainComposition: React.FC<Props> = ({data}) => {
  const {durationInFrames, fps} = useVideoConfig();
  const endingFrames = Math.min(150, Math.max(90, Math.floor(durationInFrames * 0.08)));
  const endingStart = Math.max(0, durationInFrames - endingFrames);
  const backgroundLoopFrames = Math.max(1, Math.round((data.background_duration || 8) * fps));

  return (
    <AbsoluteFill style={{backgroundColor: bg}}>
      {data.background ? (
        <AbsoluteFill>
          <Loop durationInFrames={backgroundLoopFrames}>
            <AbsoluteFill>
              <OffthreadVideo
                src={staticFile(data.background)}
                muted
                loop
                style={{width: "100%", height: "100%", objectFit: "cover", filter: "brightness(0.48) saturate(0.9)"}}
              />
            </AbsoluteFill>
          </Loop>
        </AbsoluteFill>
      ) : (
        <AbsoluteFill style={{background: "linear-gradient(135deg, #111827 0%, #101828 45%, #06111f 100%)"}} />
      )}

      {data.audio && <Audio src={staticFile(data.audio)} />}

      {data.scenes.map((scene, i) => {
        const timing = useSceneTime(scene);
        return (
          <Sequence key={`${scene.start}-${i}`} from={timing.from} durationInFrames={timing.durationInFrames}>
            <SceneTransition durationInFrames={timing.durationInFrames}>
              <RenderScene scene={scene} />
            </SceneTransition>
          </Sequence>
        );
      })}

      <Sequence from={endingStart} durationInFrames={durationInFrames - endingStart}>
        <SceneTransition durationInFrames={durationInFrames - endingStart}>
          <EndingCard data={data} />
        </SceneTransition>
      </Sequence>

      <FrameChrome data={data} />
    </AbsoluteFill>
  );
};
