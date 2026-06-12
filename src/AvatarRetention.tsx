import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {CameraMotionBlur} from '@remotion/motion-blur';
import {linearTiming} from '@remotion/transitions';
import {format as d3Format} from 'd3-format';
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  CircleDollarSign,
  ReceiptText,
} from 'lucide-react';
import type {LucideIcon} from 'lucide-react';
import type {CSSProperties} from 'react';
import type {AvatarPlan, ImageInsert, OverlayEvent, ZoomEvent} from './types';

export const AvatarRetention = ({data}: {data: AvatarPlan}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const seconds = frame / fps;
  const transform = cameraTransform(data.zooms, seconds, frame);
  const avatarVideo = data.avatarVideo?.trim();

  return (
    <AbsoluteFill style={styles.stage}>
      <AbsoluteFill style={styles.videoShell}>
        {avatarVideo ? (
          <OffthreadVideo
            src={staticFile(avatarVideo)}
            style={{
              ...styles.avatarVideo,
              transform,
            }}
            volume={1}
          />
        ) : (
          <div style={styles.missingVideo}>Build a project from the app, then reopen Studio.</div>
        )}
      </AbsoluteFill>
      <AbsoluteFill style={styles.vignette} />
      <SubtleMotionTexture />
      <SfxLayer data={data} />
      {data.images.map((image, index) => (
        <ImageInsertLayer key={`${image.path}-${index}`} image={image} />
      ))}
      {data.overlays.map((overlay, index) => (
        <OverlayLayer key={`${overlay.time}-${index}`} overlay={overlay} />
      ))}
    </AbsoluteFill>
  );
};

const cameraTransform = (zooms: ZoomEvent[], seconds: number, frame: number) => {
  const index = zooms.findIndex((zoom) => seconds >= zoom.start && seconds <= zoom.end);
  const active = index >= 0 ? zooms[index] : null;
  if (!active) {
    const previous = [...zooms].reverse().find((zoom) => seconds > zoom.end);
    if (previous) {
      return `scale(${previous.scale}) translate(${previous.x}%, ${previous.y}%)`;
    }
    return 'scale(1) translate(0%, 0%)';
  }
  const mode = active.mode ?? 'slow';
  const progress = clamp01((seconds - active.start) / Math.max(0.001, active.end - active.start));
  const previous = index > 0 ? zooms[index - 1] : null;
  const fromScale = active.fromScale ?? previous?.scale ?? (mode === 'punch' || mode === 'flash' ? 1.02 : 1);
  const fromX = active.fromX ?? previous?.x ?? 0;
  const fromY = active.fromY ?? previous?.y ?? 0;
  const eased = mode === 'punch' || mode === 'flash' ? easeOutExpo(progress) : easeInOut(progress);
  const bump = mode === 'punch' || mode === 'flash' ? Math.sin(progress * Math.PI) * 0.006 : 0;
  const scale = fromScale + (active.scale - fromScale) * eased + bump;
  const x = fromX + (active.x - fromX) * eased;
  const y = fromY + (active.y - fromY) * eased;
  return `scale(${scale}) translate(${x}%, ${y}%)`;
};

const clamp01 = (t: number) => Math.max(0, Math.min(1, t));

const easeInOut = (t: number) => {
  const clamped = clamp01(t);
  return clamped < 0.5 ? 2 * clamped * clamped : 1 - Math.pow(-2 * clamped + 2, 2) / 2;
};

const easeOutExpo = (t: number) => {
  const clamped = clamp01(t);
  return clamped === 1 ? 1 : 1 - Math.pow(2, -9 * clamped);
};

const editorialCardKinds = new Set([
  'form_highlight',
  'receipt_stack',
  'rule_slate',
  'mistake_teardown',
  'deadline_flip',
  'money_leak',
  'checklist_reveal',
  'document_scan',
  'tax_card',
  'warning_card',
  'deadline_card',
  'money_card',
  'checklist_card',
]);

const avatarCalloutKinds = new Set(['soft_caption', 'underline_callout', 'strike_callout', 'mistake_strip']);

const normalizeCardKind = (kind: OverlayEvent['kind']): OverlayEvent['kind'] => {
  if (kind === 'tax_card') return 'form_highlight';
  if (kind === 'warning_card') return 'mistake_teardown';
  if (kind === 'deadline_card') return 'deadline_flip';
  if (kind === 'money_card') return 'money_leak';
  if (kind === 'checklist_card') return 'checklist_reveal';
  return kind;
};

const SfxLayer = ({data}: {data: AvatarPlan}) => {
  const {fps} = useVideoConfig();
  const sourceFor = (name?: string) => {
    if (!name) return null;
    const src = data.sfx?.[name]?.trim();
    return src || null;
  };
  return (
    <>
      {data.overlays.map((overlay, index) => {
        const src = sourceFor(overlay.sfx);
        if (!src) return null;
        const duration = overlay.sfx === 'whoosh' ? 18 : overlay.sfx === 'hit' ? 14 : 9;
        const volume = overlay.sfx === 'hit' ? 0.11 : overlay.sfx === 'whoosh' ? 0.09 : 0.07;
        return (
          <Sequence key={`sfx-${index}`} from={Math.round(overlay.time * fps)} durationInFrames={duration}>
            <Audio src={staticFile(src)} volume={volume} />
          </Sequence>
        );
      })}
      {data.images.map((image, index) => {
        const src = sourceFor('whoosh');
        if (!src) return null;
        return (
          <Sequence key={`image-sfx-${index}`} from={Math.round(image.time * fps)} durationInFrames={18}>
            <Audio src={staticFile(src)} volume={0.075} />
          </Sequence>
        );
      })}
    </>
  );
};

const ImageInsertLayer = ({image}: {image: ImageInsert}) => {
  if (!image.path?.trim()) return null;
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const from = Math.round(image.time * fps);
  const duration = Math.round(image.duration * fps);
  const local = frame - from;
  if (local < 0 || local >= duration) return null;
  const fade = Math.min(
    interpolate(local, [0, 10], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}),
    interpolate(local, [duration - 12, duration], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}),
  );
  const progress = local / Math.max(1, duration);
  const scale = 1.035 + progress * 0.045;
  const slide = interpolate(local, [0, 16], [48, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{...styles.imageOverlay, opacity: fade}}>
      <div style={styles.imagePanel}>
        <Img src={staticFile(image.path)} style={{...styles.image, transform: `scale(${scale}) translateX(${-slide * 0.1}px)`}} />
        <div style={styles.imageShade} />
        <div style={{...styles.imageCaption, transform: `translateY(${slide}px)`}}>
          <span style={styles.yellowDot} />
          {image.caption}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const OverlayLayer = ({overlay}: {overlay: OverlayEvent}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const from = Math.round(overlay.time * fps);
  const duration = Math.round(overlay.duration * fps);
  const local = frame - from;
  if (local < 0 || local >= duration) return null;

  if (overlay.kind === 'title_card') {
    return <TitleCard overlay={overlay} local={local} duration={duration} />;
  }
  if (avatarCalloutKinds.has(overlay.kind)) {
    return <FullCardCallout overlay={overlay} local={local} duration={duration} />;
  }
  if (editorialCardKinds.has(overlay.kind)) {
    return <EditorialCard overlay={overlay} local={local} duration={duration} />;
  }
  return null;
};

const FullCardCallout = ({overlay, local, duration}: {overlay: OverlayEvent; local: number; duration: number}) => {
  const {fps} = useVideoConfig();
  const pop = spring({frame: local, fps, config: {damping: 17, stiffness: 125}});
  const out = interpolate(local, [duration - 12, duration], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const line = interpolate(local, [12, 28], [0, 100], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const underline = interpolate(local, [10, 28], [0, 100], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const isCorrection = overlay.kind === 'strike_callout' || overlay.kind === 'mistake_strip';
  const label = overlay.label || (isCorrection ? 'WATCH THIS' : 'TAX NOTE');
  return (
    <AbsoluteFill style={{...styles.editorialStage, opacity: out}}>
      <CameraMotionBlur shutterAngle={95} samples={6}>
        <div
          style={{
            ...styles.fullCalloutCard,
            transform: `translateY(${(1 - pop) * 34}px) scale(${0.965 + pop * 0.035})`,
          }}
        >
          <div style={{...styles.fullCalloutLabel, color: isCorrection ? '#ff4d4d' : '#555555'}}>{label}</div>
          <div style={styles.fullCalloutTextWrap}>
            <div style={styles.fullCalloutText}>{overlay.text.toUpperCase()}</div>
            {isCorrection ? <div style={{...styles.fullCalloutStrike, width: `${line}%`}} /> : null}
          </div>
          {!isCorrection ? <div style={{...styles.fullCalloutUnderline, width: `${underline}%`}} /> : null}
        </div>
      </CameraMotionBlur>
    </AbsoluteFill>
  );
};

const titleWithoutDuplicateNumber = (text: string, number?: number) => {
  const trimmed = text.trim();
  if (number) {
    return trimmed.replace(new RegExp(`^${number}[.)\\]:-]?\\s+`, 'i'), '').trim() || trimmed;
  }
  return trimmed.replace(/^(?:#?\d{1,2}|[IVX]{1,5})[.)\]:-]?\s+/i, '').trim() || trimmed;
};

const TitleCard = ({overlay, local, duration}: {overlay: OverlayEvent; local: number; duration: number}) => {
  const {fps} = useVideoConfig();
  const pop = spring({frame: local, fps, config: {damping: 15, stiffness: 140}});
  const out = interpolate(local, [duration - 10, duration], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const titleText = titleWithoutDuplicateNumber(overlay.text, overlay.number);
  return (
    <AbsoluteFill style={{...styles.titleCard, opacity: out}}>
      <CameraMotionBlur shutterAngle={80} samples={5}>
        <div style={styles.titleCardInner}>
          {overlay.number ? (
            <div style={{...styles.titleNumber, transform: `scale(${0.84 + pop * 0.16})`}}>{overlay.number}</div>
          ) : null}
          <div style={{...styles.titleText, transform: `translateY(${(1 - pop) * 24}px)`}}>{titleText}</div>
        </div>
      </CameraMotionBlur>
    </AbsoluteFill>
  );
};

const EditorialCard = ({overlay, local, duration}: {overlay: OverlayEvent; local: number; duration: number}) => {
  const {fps} = useVideoConfig();
  const enter = linearTiming({durationInFrames: 16, easing: easeOutExpo}).getProgress({frame: local, fps});
  const exit = interpolate(local, [duration - 12, duration], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const progress = Math.min(enter, exit);
  const kind = normalizeCardKind(overlay.kind);
  const tone = overlay.tone ?? toneFromKind(kind);
  const iconName: NonNullable<OverlayEvent['icon']> = overlay.icon ?? iconFromTone(tone) ?? 'receipt';
  const Icon = iconMap[iconName] ?? ReceiptText;
  const meter = clamp01(overlay.meter ?? meterFromTone(tone));
  const meterWidth = 720 * meter;
  const y = interpolate(local, [0, 18], [34, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const value = formatValue(overlay.value);
  const items = overlayItems(overlay);

  return (
    <AbsoluteFill style={{...styles.editorialStage, opacity: progress}}>
      <CameraMotionBlur shutterAngle={100} samples={6}>
        <div style={{...styles.editorialMotion, transform: `translateY(${y}px) scale(${0.965 + enter * 0.035})`}}>
          {kind === 'receipt_stack' ? (
            <ReceiptStack overlay={overlay} icon={Icon} tone={tone} value={value} meterWidth={meterWidth} items={items} />
          ) : kind === 'mistake_teardown' ? (
            <MistakeTeardown overlay={overlay} icon={Icon} tone={tone} items={items} />
          ) : kind === 'deadline_flip' ? (
            <DeadlineFlip overlay={overlay} icon={Icon} value={value} />
          ) : kind === 'money_leak' ? (
            <MoneyLeak overlay={overlay} local={local} duration={duration} />
          ) : kind === 'checklist_reveal' ? (
            <ChecklistReveal overlay={overlay} icon={Icon} local={local} items={items} />
          ) : kind === 'document_scan' ? (
            <DocumentScan overlay={overlay} icon={Icon} local={local} tone={tone} items={items} />
          ) : kind === 'rule_slate' ? (
            <RuleSlate overlay={overlay} icon={Icon} tone={tone} value={value} meterWidth={meterWidth} items={items} />
          ) : (
            <FormHighlight overlay={overlay} icon={Icon} tone={tone} value={value} meterWidth={meterWidth} items={items} />
          )}
        </div>
      </CameraMotionBlur>
    </AbsoluteFill>
  );
};

const FormHighlight = ({
  overlay,
  icon: Icon,
  tone,
  value,
  meterWidth,
  items,
}: {
  overlay: OverlayEvent;
  icon: LucideIcon;
  tone: OverlayEvent['tone'];
  value: string | null;
  meterWidth: number;
  items: string[];
}) => (
  <div style={styles.formCard}>
    <div style={{...styles.cardIconBox, backgroundColor: colorFromTone(tone)}}>
      <Icon size={58} strokeWidth={2.5} />
    </div>
    <div style={styles.formContent}>
      <div style={styles.cardLabel}>{overlay.label || labelFromTone(tone)}</div>
      <div style={styles.formHeadline}>{overlay.text.toUpperCase()}</div>
      {value ? <div style={styles.valuePill}>{value}</div> : null}
      {items.length ? (
        <div style={styles.simpleItems}>
          {items.slice(0, 4).map((item) => (
            <div key={item} style={styles.simpleItem}>
              <CheckCircle2 size={27} strokeWidth={2.4} />
              <span>{item.toUpperCase()}</span>
            </div>
          ))}
        </div>
      ) : (
        <div style={styles.cardMeterTrack}>
          <div style={{...styles.cardMeterFill, width: meterWidth, backgroundColor: colorFromTone(tone)}} />
        </div>
      )}
    </div>
    <div style={styles.formGhostCircle} />
  </div>
);

const ReceiptStack = ({
  overlay,
  icon: Icon,
  tone,
  value,
  meterWidth,
  items,
}: {
  overlay: OverlayEvent;
  icon: LucideIcon;
  tone: OverlayEvent['tone'];
  value: string | null;
  meterWidth: number;
  items: string[];
}) => (
  <div style={styles.receiptScene}>
    <div style={{...styles.receiptPaper, transform: 'rotate(-4deg) translateX(-48px)'}} />
    <div style={{...styles.receiptPaper, transform: 'rotate(3deg) translateX(44px)', opacity: 0.72}} />
    <div style={styles.receiptTop}>
      <div style={{...styles.cardIconBox, backgroundColor: colorFromTone(tone)}}>
        <Icon size={56} strokeWidth={2.5} />
      </div>
      <div>
        <div style={styles.cardLabel}>{overlay.label || 'RECEIPT CHECK'}</div>
        <div style={styles.receiptHeadline}>{overlay.text.toUpperCase()}</div>
      </div>
    </div>
    <div style={styles.receiptRows}>
      {(items.length ? items : ['SAVE THE RECEIPT', 'MATCH THE FORM', 'CHECK THE TOTAL']).slice(0, 3).map((item) => (
        <div key={item} style={styles.receiptRow}>
          <span>{item}</span>
          <span>{value || 'VERIFY'}</span>
        </div>
      ))}
    </div>
    <div style={styles.cardMeterTrack}>
      <div style={{...styles.cardMeterFill, width: meterWidth, backgroundColor: colorFromTone(tone)}} />
    </div>
  </div>
);

const RuleSlate = ({
  overlay,
  icon: Icon,
  tone,
  value,
  meterWidth,
  items,
}: {
  overlay: OverlayEvent;
  icon: LucideIcon;
  tone: OverlayEvent['tone'];
  value: string | null;
  meterWidth: number;
  items: string[];
}) => (
  <div style={styles.ruleSlate}>
    <div style={styles.ruleGrid}>
      <div style={{...styles.cardIconBox, ...styles.ruleIcon}}>
        <Icon size={58} strokeWidth={2.4} />
      </div>
      <div style={styles.cardLabel}>{overlay.label || 'RULE CHANGE'}</div>
      <div style={styles.ruleHeadline}>{overlay.text.toUpperCase()}</div>
      {value ? <div style={styles.ruleValue}>{value}</div> : null}
      {items.length ? (
        <div style={styles.simpleItems}>
          {items.slice(0, 3).map((item) => (
            <div key={item} style={styles.simpleItem}>
              <CheckCircle2 size={27} strokeWidth={2.4} />
              <span>{item.toUpperCase()}</span>
            </div>
          ))}
        </div>
      ) : (
        <div style={styles.cardMeterTrack}>
          <div style={{...styles.cardMeterFill, width: meterWidth, backgroundColor: colorFromTone(tone)}} />
        </div>
      )}
    </div>
  </div>
);

const MistakeTeardown = ({
  overlay,
  icon: Icon,
  tone,
  items,
}: {
  overlay: OverlayEvent;
  icon: LucideIcon;
  tone: OverlayEvent['tone'];
  items: string[];
}) => {
  const left = items[0] || 'COMMON MISTAKE';
  const right = items[1] || overlay.text;
  return (
    <div style={styles.teardown}>
      <div style={styles.teardownHeader}>
        <div style={{...styles.cardIconBox, backgroundColor: colorFromTone(tone)}}>
          <Icon size={56} strokeWidth={2.6} />
        </div>
        <div>
          <div style={styles.cardLabel}>{overlay.label || 'MISTAKE CHECK'}</div>
          <div style={styles.teardownHeadline}>{overlay.text.toUpperCase()}</div>
        </div>
      </div>
      <div style={styles.teardownColumns}>
        <div style={styles.teardownBad}>{left.toUpperCase()}</div>
        <div style={styles.teardownGood}>{right.toUpperCase()}</div>
      </div>
    </div>
  );
};

const DeadlineFlip = ({overlay, icon: Icon, value}: {overlay: OverlayEvent; icon: LucideIcon; value: string | null}) => {
  const headline = value ? value : overlay.text.toUpperCase();
  const subline = value ? overlay.text.toUpperCase() : 'FILE EARLY. PAY ON TIME.';
  return (
    <div style={styles.deadlineCard}>
      <div style={{...styles.deadlineIconTile, backgroundColor: value ? '#ffd43b' : 'transparent'}}>
        <Icon size={70} strokeWidth={2.25} />
      </div>
      <div style={styles.deadlineText}>
        <div style={styles.cardLabel}>{overlay.label || 'DEADLINE'}</div>
        <div style={styles.deadlineHeadline}>{headline}</div>
        <div style={styles.deadlineSubline}>{subline}</div>
      </div>
    </div>
  );
};

const MoneyLeak = ({overlay, local, duration}: {overlay: OverlayEvent; local: number; duration: number}) => {
  const {fps} = useVideoConfig();
  const pop = spring({frame: local, fps, config: {damping: 17, stiffness: 120}});
  const underline = interpolate(local, [14, 30], [0, 100], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const out = interpolate(local, [duration - 12, duration], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <div style={{...styles.impactCard, opacity: out}}>
      <div style={styles.impactLabel}>{overlay.label || 'TAX MISTAKES'}</div>
      <div style={{...styles.impactHeadline, transform: `translateY(${(1 - pop) * 28}px) scale(${0.96 + pop * 0.04})`}}>
        {overlay.text.toUpperCase()}
      </div>
      <div style={{...styles.impactUnderline, width: `${underline}%`}} />
    </div>
  );
};

const normalizeChecklistItem = (item: string) => item.toUpperCase().replace(/[^A-Z0-9]+/g, '');

const checklistDisplayItems = (overlay: OverlayEvent, items: string[]) => {
  const headline = overlay.text.toUpperCase();
  if (headline.includes('DEDUCT EXPENSES')) {
    const base = ['MILEAGE', 'INTERNET', 'EQUIPMENT', 'SOFTWARE'];
    const merged = [...items.map((item) => item.toUpperCase())];
    for (const item of base) {
      if (!merged.some((existing) => normalizeChecklistItem(existing) === normalizeChecklistItem(item))) {
        merged.push(item);
      }
    }
    return merged.slice(0, 4);
  }
  return (items.length ? items : ['MILEAGE', 'INTERNET', 'EQUIPMENT']).map((item) => item.toUpperCase()).slice(0, 4);
};

const ChecklistReveal = ({
  overlay,
  icon: Icon,
  local,
  items,
}: {
  overlay: OverlayEvent;
  icon: LucideIcon;
  local: number;
  items: string[];
}) => (
  <div style={styles.checklistCard}>
    <div style={styles.checklistTitleRow}>
      <div style={{...styles.cardIconBox, ...styles.checklistIconBox}}>
        <Icon size={54} strokeWidth={2.5} />
      </div>
      <div>
        <div style={styles.cardLabel}>{overlay.label || 'CHECKLIST'}</div>
        <div style={styles.checklistHeadline}>{overlay.text.toUpperCase()}</div>
      </div>
    </div>
    <div style={styles.checklistItems}>
      {checklistDisplayItems(overlay, items).map((item, index) => {
        const activeKeys = new Set(items.map(normalizeChecklistItem));
        const latest = normalizeChecklistItem(items[items.length - 1] || '');
        const active = activeKeys.has(normalizeChecklistItem(item));
        const isLatest = latest === normalizeChecklistItem(item);
        const reveal = interpolate(local, [8, 22], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
        const lift = isLatest ? interpolate(local, [4, 18], [22, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}) : 0;
        return (
          <div
            key={`${item}-${index}`}
            style={{
              ...styles.checklistItem,
              opacity: active ? 0.98 : 0.2,
              filter: active ? 'blur(0px)' : 'blur(5px)',
              transform: `translateX(${active ? 0 : 10}px) translateY(${lift}px)`,
            }}
          >
            <CheckCircle2 size={30} strokeWidth={2.5} style={{opacity: active ? reveal : 0.28}} />
            <span>{item}</span>
            {isLatest ? <span style={{...styles.checklistRevealLine, transform: `scaleX(${reveal})`}} /> : null}
          </div>
        );
      })}
    </div>
  </div>
);

const DocumentScan = ({
  overlay,
  icon: Icon,
  local,
  tone,
  items,
}: {
  overlay: OverlayEvent;
  icon: LucideIcon;
  local: number;
  tone: OverlayEvent['tone'];
  items: string[];
}) => {
  const scanY = interpolate(local, [0, 40], [70, 276], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <div style={styles.documentScan}>
      <div style={styles.documentPage}>
        <div style={styles.docHeader}>
          <Icon size={42} strokeWidth={2.4} />
          <span>{overlay.label || 'DOCUMENT SCAN'}</span>
        </div>
        <div style={{...styles.scanLine, top: scanY, backgroundColor: colorFromTone(tone)}} />
        {(items.length ? items : ['FORM LINE', 'REPORTED AMOUNT', 'SUPPORTING PROOF']).slice(0, 3).map((item, index) => (
          <div key={item} style={{...styles.docLine, width: 520 - index * 70}}>
            {item.toUpperCase()}
          </div>
        ))}
      </div>
      <div style={styles.documentHeadline}>{overlay.text.toUpperCase()}</div>
    </div>
  );
};

const toneFromKind = (kind: OverlayEvent['kind']) => {
  if (kind === 'mistake_teardown' || kind === 'warning_card') return 'warning';
  if (kind === 'deadline_flip' || kind === 'deadline_card') return 'deadline';
  if (kind === 'money_leak' || kind === 'money_card') return 'money';
  if (kind === 'document_scan') return 'audit';
  return 'audit';
};

const iconFromTone = (tone: OverlayEvent['tone'] = 'neutral'): OverlayEvent['icon'] => {
  if (tone === 'money') return 'dollar';
  if (tone === 'deadline') return 'calendar';
  if (tone === 'warning' || tone === 'audit') return 'warning';
  return 'receipt';
};

const labelFromTone = (tone: OverlayEvent['tone'] = 'neutral') => {
  if (tone === 'money') return 'MONEY CHECK';
  if (tone === 'deadline') return 'DEADLINE';
  if (tone === 'warning') return 'WATCH THIS';
  if (tone === 'audit') return 'IRS RISK';
  return 'TAX NOTE';
};

const colorFromTone = (tone: OverlayEvent['tone'] = 'neutral') => {
  if (tone === 'warning' || tone === 'audit') return '#ff4d4d';
  if (tone === 'deadline') return '#111111';
  return '#ffd43b';
};

const meterFromTone = (tone: OverlayEvent['tone'] = 'neutral') => {
  if (tone === 'warning' || tone === 'audit') return 0.82;
  if (tone === 'deadline') return 0.72;
  if (tone === 'money') return 0.64;
  return 0.5;
};

const formatValue = (value?: string) => {
  if (!value) return null;
  const trimmed = value.trim();
  const numeric = Number(trimmed.replace(/[$,%\s,]/g, ''));
  if (!Number.isFinite(numeric)) return trimmed.slice(0, 18);
  if (trimmed.includes('%')) return `${d3Format(',.0f')(numeric)}%`;
  if (trimmed.includes('$')) return `$${d3Format(',.0f')(numeric)}`;
  return d3Format(',.0f')(numeric);
};

const overlayItems = (overlay: OverlayEvent) => {
  if (overlay.items?.length) return overlay.items.map((item) => item.trim()).filter(Boolean).slice(0, 4);
  return overlay.text
    .split(/[;|]/)
    .map((part) => part.trim())
    .filter(Boolean)
    .slice(0, 4);
};

const iconMap: Record<NonNullable<OverlayEvent['icon']>, LucideIcon> = {
  receipt: ReceiptText,
  warning: AlertTriangle,
  calendar: CalendarDays,
  dollar: CircleDollarSign,
  check: CheckCircle2,
};

const SubtleMotionTexture = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill
      style={{
        ...styles.texture,
        opacity: 0.025 + Math.sin(frame * 0.045) * 0.004,
      }}
    />
  );
};

const styles: Record<string, CSSProperties> = {
  stage: {
    backgroundColor: '#080808',
    overflow: 'hidden',
    fontFamily: 'Inter, Arial, Helvetica, sans-serif',
  },
  videoShell: {
    overflow: 'hidden',
    backgroundColor: '#050505',
  },
  avatarVideo: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
    transformOrigin: '50% 50%',
    willChange: 'transform',
  },
  missingVideo: {
    width: '100%',
    height: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#f2f1ea',
    fontSize: 38,
    fontWeight: 800,
    backgroundColor: '#111111',
  },
  vignette: {
    background:
      'radial-gradient(circle at center, rgba(0,0,0,0) 42%, rgba(0,0,0,0.18) 78%, rgba(0,0,0,0.42) 100%)',
    pointerEvents: 'none',
  },
  texture: {
    background:
      'linear-gradient(90deg, rgba(255,255,255,.05) 1px, transparent 1px), linear-gradient(rgba(255,255,255,.04) 1px, transparent 1px)',
    backgroundSize: '42px 42px',
    mixBlendMode: 'overlay',
  },
  titleCard: {
    backgroundColor: '#f2f1ea',
    color: '#111',
  },
  titleCardInner: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 28,
    display: 'flex',
    flexDirection: 'row',
  },
  titleNumber: {
    width: 92,
    height: 92,
    borderRadius: 18,
    backgroundColor: '#ffd43b',
    color: '#fff',
    fontSize: 62,
    fontWeight: 900,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 18px 40px rgba(0,0,0,.18)',
  },
  titleText: {
    maxWidth: 980,
    fontSize: 62,
    lineHeight: 1.02,
    fontWeight: 900,
    letterSpacing: 0,
  },
  fullCalloutCard: {
    width: '100%',
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    textAlign: 'center',
    padding: '0 180px',
    willChange: 'transform',
  },
  fullCalloutLabel: {
    fontSize: 30,
    fontWeight: 900,
    textTransform: 'uppercase',
    marginBottom: 22,
  },
  fullCalloutTextWrap: {
    position: 'relative',
    display: 'inline-block',
    maxWidth: 1220,
  },
  fullCalloutText: {
    fontSize: 74,
    lineHeight: 1.03,
    fontWeight: 1000,
    letterSpacing: 0,
  },
  fullCalloutStrike: {
    position: 'absolute',
    left: '50%',
    top: '54%',
    height: 10,
    backgroundColor: '#ff4d4d',
    transform: 'translateX(-50%)',
    transformOrigin: 'center center',
    boxShadow: '0 8px 20px rgba(255,77,77,.22)',
  },
  fullCalloutUnderline: {
    height: 12,
    backgroundColor: '#ffd43b',
    marginTop: 24,
    maxWidth: 720,
    boxShadow: '0 10px 26px rgba(0,0,0,.12)',
  },
  underlineCallout: {
    position: 'absolute',
    left: '50%',
    bottom: 142,
    color: '#fffdf5',
    fontSize: 56,
    fontWeight: 1000,
    lineHeight: 1.02,
    textAlign: 'center',
    maxWidth: 1260,
    textShadow: '0 8px 30px rgba(0,0,0,.72), 0 2px 2px rgba(0,0,0,.7)',
  },
  progressiveWord: {
    display: 'inline-block',
    marginRight: 14,
    willChange: 'transform, opacity',
  },
  yellowUnderline: {
    height: 10,
    backgroundColor: '#ffd43b',
    margin: '16px auto 0',
    boxShadow: '0 6px 18px rgba(0,0,0,.28)',
  },
  strikeCallout: {
    position: 'absolute',
    left: '50%',
    bottom: 142,
    color: '#fffdf5',
    fontSize: 52,
    fontWeight: 1000,
    lineHeight: 1.02,
    textAlign: 'center',
    maxWidth: 1180,
    textShadow: '0 8px 30px rgba(0,0,0,.72), 0 2px 2px rgba(0,0,0,.7)',
  },
  redStrike: {
    height: 9,
    backgroundColor: '#ff4d4d',
    margin: '-34px auto 0',
    transform: 'rotate(0deg)',
    boxShadow: '0 5px 14px rgba(0,0,0,.24)',
  },
  softCaption: {
    position: 'absolute',
    left: 94,
    bottom: 128,
    color: '#fffdf5',
    fontSize: 44,
    fontWeight: 950,
    lineHeight: 1.06,
    maxWidth: 920,
    textShadow: '0 8px 30px rgba(0,0,0,.72), 0 2px 2px rgba(0,0,0,.7)',
  },
  softCaptionLabel: {
    color: '#ffd43b',
    fontSize: 24,
    fontWeight: 1000,
    marginBottom: 8,
    textShadow: '0 6px 22px rgba(0,0,0,.7)',
  },
  softCaptionUnderline: {
    height: 8,
    backgroundColor: '#ffd43b',
    marginTop: 14,
    maxWidth: 520,
  },
  mistakeStrip: {
    position: 'absolute',
    left: '50%',
    bottom: 142,
    color: '#fffdf5',
    maxWidth: 1180,
    fontSize: 54,
    fontWeight: 1000,
    lineHeight: 1.02,
    textAlign: 'center',
    textShadow: '0 8px 30px rgba(0,0,0,.72), 0 2px 2px rgba(0,0,0,.7)',
  },
  mistakeLabel: {
    color: '#ffd43b',
    fontSize: 24,
    fontWeight: 1000,
    marginBottom: 12,
  },
  mistakeLine: {
    display: 'flex',
    alignItems: 'center',
    gap: 30,
    fontSize: 42,
    fontWeight: 1000,
  },
  mistakeWrong: {
    position: 'relative',
    display: 'inline-block',
    color: '#fffdf5',
  },
  inlineStrike: {
    position: 'absolute',
    left: 0,
    top: '52%',
    height: 8,
    backgroundColor: '#ff4d4d',
    transform: 'rotate(0deg)',
    transformOrigin: 'left center',
  },
  mistakeFix: {
    color: '#ffd43b',
    borderBottom: '8px solid #ffd43b',
    paddingBottom: 6,
  },
  editorialStage: {
    backgroundColor: '#f2f1ea',
    color: '#111111',
    alignItems: 'center',
    justifyContent: 'center',
  },
  editorialMotion: {
    width: '100%',
    height: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardIconBox: {
    width: 122,
    height: 122,
    color: '#111111',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 18px 42px rgba(0,0,0,.16)',
    flex: '0 0 auto',
  },
  cardLabel: {
    fontSize: 28,
    fontWeight: 900,
    color: '#555555',
    marginBottom: 12,
    textTransform: 'uppercase',
  },
  cardMeterTrack: {
    width: 720,
    height: 12,
    backgroundColor: 'rgba(17,17,17,.13)',
    marginTop: 34,
    overflow: 'hidden',
  },
  cardMeterFill: {
    height: '100%',
  },
  formCard: {
    position: 'relative',
    width: 1120,
    minHeight: 390,
    backgroundColor: 'transparent',
    border: 'none',
    boxShadow: 'none',
    display: 'flex',
    alignItems: 'center',
    gap: 46,
    padding: '42px 54px',
    overflow: 'hidden',
  },
  formContent: {
    flex: 1,
    minWidth: 0,
    zIndex: 1,
  },
  formHeadline: {
    fontSize: 58,
    fontWeight: 1000,
    lineHeight: 1.02,
    maxWidth: 940,
  },
  valuePill: {
    display: 'inline-flex',
    alignItems: 'center',
    backgroundColor: '#111111',
    color: '#ffffff',
    fontSize: 48,
    fontWeight: 1000,
    padding: '10px 20px',
    marginTop: 20,
  },
  formGhostCircle: {
    position: 'absolute',
    right: -130,
    top: -100,
    width: 360,
    height: 360,
    borderRadius: '50%',
    border: '34px solid rgba(17,17,17,.025)',
  },
  simpleItems: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 16,
    marginTop: 32,
    maxWidth: 900,
  },
  simpleItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 14,
    borderBottom: '7px solid #ffd43b',
    padding: '10px 6px 12px 0',
    color: '#111111',
    fontSize: 28,
    fontWeight: 950,
    lineHeight: 1,
  },
  receiptScene: {
    position: 'relative',
    width: 1240,
    minHeight: 620,
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
    gap: 32,
    padding: '64px 82px',
  },
  receiptPaper: {
    position: 'absolute',
    inset: '42px 160px',
    backgroundColor: '#fffdf5',
    border: '2px dashed rgba(17,17,17,.2)',
    boxShadow: '0 24px 60px rgba(0,0,0,.12)',
  },
  receiptTop: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: 38,
  },
  receiptHeadline: {
    fontSize: 58,
    fontWeight: 1000,
    lineHeight: 1.02,
    maxWidth: 840,
  },
  receiptRows: {
    position: 'relative',
    width: 820,
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
    fontSize: 30,
    fontWeight: 850,
  },
  receiptRow: {
    display: 'flex',
    justifyContent: 'space-between',
    borderBottom: '2px solid rgba(17,17,17,.12)',
    padding: '12px 0',
  },
  ruleSlate: {
    width: 1120,
    minHeight: 440,
    backgroundColor: 'transparent',
    color: '#111111',
    border: 'none',
    boxShadow: 'none',
    padding: '48px 66px',
  },
  ruleGrid: {
    height: '100%',
    display: 'grid',
    gridTemplateColumns: '150px 1fr',
    alignItems: 'center',
    columnGap: 42,
  },
  ruleIcon: {
    gridRow: '1 / span 4',
    backgroundColor: '#ffd43b',
  },
  ruleHeadline: {
    fontSize: 62,
    fontWeight: 1000,
    lineHeight: 1.02,
    maxWidth: 860,
  },
  ruleValue: {
    fontSize: 84,
    fontWeight: 1000,
    lineHeight: 1,
    color: '#ffd43b',
    marginTop: 8,
  },
  teardown: {
    width: 1260,
    minHeight: 560,
    backgroundColor: '#fffdf5',
    border: '2px solid rgba(17,17,17,.12)',
    boxShadow: '0 34px 85px rgba(0,0,0,.16)',
    padding: '62px 72px',
  },
  teardownHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 36,
    marginBottom: 42,
  },
  teardownHeadline: {
    fontSize: 54,
    fontWeight: 1000,
    lineHeight: 1.04,
    maxWidth: 900,
  },
  teardownColumns: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 28,
    fontSize: 38,
    fontWeight: 950,
    lineHeight: 1.08,
  },
  teardownBad: {
    backgroundColor: '#fff7d4',
    color: '#111111',
    padding: '34px 36px',
    borderLeft: '12px solid #ff4d4d',
    minHeight: 138,
  },
  teardownGood: {
    backgroundColor: '#fffdf5',
    color: '#111111',
    padding: '34px 36px',
    borderBottom: '12px solid #ffd43b',
    minHeight: 138,
  },
  deadlineCard: {
    width: 1080,
    minHeight: 420,
    display: 'grid',
    gridTemplateColumns: '140px 1fr',
    gap: 44,
    alignItems: 'center',
  },
  deadlineIconTile: {
    width: 116,
    height: 116,
    color: '#111111',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  calendarPanel: {
    height: 360,
    backgroundColor: '#fffdf5',
    border: '3px solid #111111',
    boxShadow: '0 30px 70px rgba(0,0,0,.14)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  calendarTop: {
    backgroundColor: '#ffd43b',
    color: '#111111',
    fontSize: 32,
    fontWeight: 950,
    padding: '24px 26px',
  },
  calendarValue: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 74,
    fontWeight: 1000,
  },
  deadlineText: {
    position: 'relative',
  },
  deadlineHeadline: {
    fontSize: 72,
    fontWeight: 1000,
    lineHeight: 1.02,
  },
  deadlineSubline: {
    color: '#555555',
    fontSize: 34,
    fontWeight: 900,
    marginTop: 22,
    textTransform: 'uppercase',
  },
  deadlineIcon: {
    marginTop: 34,
  },
  impactCard: {
    width: 1220,
    minHeight: 470,
    backgroundColor: 'transparent',
    color: '#111111',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '68px 88px',
  },
  impactLabel: {
    fontSize: 30,
    fontWeight: 950,
    color: '#555555',
    textTransform: 'uppercase',
    marginBottom: 18,
  },
  impactHeadline: {
    maxWidth: 980,
    textAlign: 'center',
    fontSize: 70,
    fontWeight: 1000,
    lineHeight: 1,
    letterSpacing: 0,
  },
  impactUnderline: {
    height: 12,
    maxWidth: 620,
    backgroundColor: '#ffd43b',
    marginTop: 28,
    transformOrigin: 'center',
    boxShadow: '0 10px 24px rgba(0,0,0,.12)',
  },
  checklistCard: {
    width: 1180,
    minHeight: 540,
    backgroundColor: 'transparent',
    padding: '62px 76px',
  },
  checklistTitleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 36,
    marginBottom: 42,
  },
  checklistIconBox: {
    backgroundColor: '#ffd43b',
    width: 116,
    height: 116,
    boxShadow: '0 20px 50px rgba(255,212,59,.22), 0 18px 42px rgba(0,0,0,.1)',
  },
  checklistHeadline: {
    fontSize: 56,
    fontWeight: 1000,
    lineHeight: 1.04,
    maxWidth: 860,
  },
  checklistItems: {
    display: 'flex',
    flexDirection: 'column',
    gap: 20,
    maxWidth: 780,
    marginLeft: 6,
  },
  checklistItem: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: 20,
    color: '#111111',
    padding: '6px 0 10px',
    fontSize: 36,
    fontWeight: 950,
    lineHeight: 1.06,
    willChange: 'transform, opacity, filter',
    transition: 'none',
  },
  checklistRevealLine: {
    position: 'absolute',
    left: 52,
    bottom: 0,
    width: 360,
    height: 8,
    backgroundColor: '#ffd43b',
    transformOrigin: 'left center',
  },
  documentScan: {
    width: 1220,
    minHeight: 560,
    display: 'grid',
    gridTemplateColumns: '520px 1fr',
    alignItems: 'center',
    gap: 58,
  },
  documentPage: {
    position: 'relative',
    height: 440,
    backgroundColor: '#fffdf5',
    border: '2px solid rgba(17,17,17,.18)',
    boxShadow: '0 30px 70px rgba(0,0,0,.14)',
    padding: '38px 42px',
    overflow: 'hidden',
  },
  docHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 14,
    fontSize: 26,
    fontWeight: 950,
    color: '#555555',
    marginBottom: 36,
  },
  scanLine: {
    position: 'absolute',
    left: 0,
    width: '100%',
    height: 12,
    opacity: 0.8,
    boxShadow: '0 0 18px rgba(255,212,59,.45)',
  },
  docLine: {
    height: 28,
    backgroundColor: 'rgba(17,17,17,.13)',
    marginBottom: 22,
  },
  documentHeadline: {
    fontSize: 62,
    fontWeight: 1000,
    lineHeight: 1.02,
  },
  imageOverlay: {
    background: 'rgba(0,0,0,.18)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  imagePanel: {
    position: 'relative',
    width: '100%',
    height: '100%',
    overflow: 'hidden',
    backgroundColor: '#111',
  },
  image: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
    transformOrigin: '50% 50%',
  },
  imageShade: {
    position: 'absolute',
    inset: 0,
    background: 'linear-gradient(0deg, rgba(0,0,0,.65), rgba(0,0,0,.05) 48%, rgba(0,0,0,.18))',
  },
  imageCaption: {
    position: 'absolute',
    left: 44,
    bottom: 36,
    color: '#fff',
    fontSize: 42,
    fontWeight: 900,
    display: 'flex',
    alignItems: 'center',
    gap: 16,
    textShadow: '0 8px 28px rgba(0,0,0,.72)',
  },
  yellowDot: {
    width: 18,
    height: 18,
    backgroundColor: '#ffd43b',
    display: 'inline-block',
  },
};
