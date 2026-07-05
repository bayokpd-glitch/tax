const path = require('path');
const {bundle} = require('@remotion/bundler');
const {renderStill, selectComposition} = require('@remotion/renderer');
const {enableTailwind} = require('@remotion/tailwind-v4');

const shots = [
  ['01_title_card', 108],
  ['02_money_leak_impact', 264],
  ['03_underline_callout', 408],
  ['04_strike_callout', 558],
  ['05_soft_caption', 708],
  ['06_mistake_strip', 858],
  ['07_form_highlight', 1014],
  ['08_receipt_stack', 1164],
  ['09_rule_slate', 1314],
  ['10_deadline_flip', 1464],
  ['11_checklist_reveal', 1614],
  ['12_document_scan', 1755],
  ['13_stat_counter', 1917],
  ['14_bar_chart', 2076],
  ['15_donut_chart', 2217],
  ['16_image_insert', 2385],
];

(async () => {
  const serveUrl = await bundle({
    entryPoint: path.join(__dirname, 'src', 'index.ts'),
    webpackOverride: enableTailwind,
    publicDir: path.join(__dirname, 'public'),
  });
  const composition = await selectComposition({serveUrl, id: 'AvatarTax'});
  const outDir = path.join(__dirname, 'out', 'demo');
  for (const [name, frame] of shots) {
    await renderStill({
      composition,
      serveUrl,
      output: path.join(outDir, `${name}.png`),
      frame,
    });
    console.log('rendered', name);
  }
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
