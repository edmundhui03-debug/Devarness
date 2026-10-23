export const meta = {
  name: 'pyrosim-guide-translate',
  description: 'Translate the PyroSim guide into Hong Kong written Chinese, one agent per chunk',
  phases: [{ title: 'Translate' }],
}

const SITE = 'Harness/guides/pyrosim/site'   // relative to the dev root, where the workflow runs

const RULES = `You are translating part of a dev workspace page into **Hong Kong written Chinese**: Traditional characters, professional register, the way a Hong Kong fire-safety engineer writes. Not Mainland phrasing, not stiff translationese, not transcribed speech. Prefer 用 over 使用, 要 over 需要, 做 over 進行, 睇 only where the register genuinely allows it (usually it does not in a written technical guide — use 看 or 查看).

INPUT: ${SITE}/chunks/en-NN.json — a flat JSON object of key -> English HTML fragment.
OUTPUT: write ${SITE}/chunks/zh-NN.json with the Write tool: the SAME keys, in the same order, each mapped to the Chinese translation of that fragment. Every key must be present. Return only "done NN, K strings".

HARD RULES:
1. **Keep the HTML identical.** If the English is \`Set <b>End Time</b> to <span class="val">60</span> s\`, the Chinese must keep the same tags around the same pieces: \`將 <b>End Time</b> 設為 <span class="val">60</span> 秒\`. Never add, drop, reorder or rename a tag or an attribute. Never translate an attribute value. Never translate anything inside <code>.
2. **These stay in English, in both languages** — tool and product names (PyroSim, FDS, Smokeview, Thunderhead, NIST, Windows, macOS), every menu item, button and dialog field name (Run FDS, Edit Meshes, Simulation Parameters, Record View, Open Mesh Boundaries, Wall Hole, Surface Type, Burner, Byproducts…), every FDS keyword and file name (MESH, OBST, HOLE, VENT, SURF, DEVC, SLCF, REAC, RAMP, HRRPUA, TAU_Q, CHID, .fds, .psm, _devc.csv, .out, .smv), every number, unit and symbol (kW, kW/m², m, s, °C, ppm, D*/δx, m^2.5), file paths, and the abbreviations HRR, CO, CO₂, O₂, FED, MPI, CSV, ISO 9705, NUREG-1805, MQH.
3. **Fixed vocabulary** — use exactly these, which stay consistent throughout this guide:
   heat release rate 放熱率 (keep "HRR" where the English uses it) · mesh 網格 · cell size 格距 · cell 網格單元 · smoke layer 煙層 · layer height 煙層高度 · hot gas layer 熱煙層 · visibility 能見度 · optical density 光學密度 · obscuration 遮光度 · soot 煙塵 · flashover flashover (keep the English word; 閃燃 only where the English itself glosses it) · tenability 可維生性 · sensor sensor (keep the English word) · detector 偵測器 · simulation 模擬 · simulation case 個案 · scenario 情景 (but PyroSim's feature name "Scenarios" stays English) · ignition 點火 · fire origin 起火位置 · device 量測裝置 · burner burner (keep the English word, it is the PyroSim surface type) · doorway 門口 · opening 開口 · compartment 隔間 · zone node 區域節點 · training data 訓練數據 · dataset 數據集 · run（模擬）運行 · wall clock time 實際運行時間.
4. **Keep the meaning exact.** This is a technical guide a beginner will follow step by step: a mistranslated instruction wastes their afternoon. If a sentence is ambiguous, translate the technically correct reading. Never soften a warning, never add advice the English does not give, never drop a caveat.
5. **Keep it readable.** Chinese technical prose is tighter than English; do not pad. Where English says "you", address the reader directly (你) rather than 使用者.
6. **Punctuation.** Use full-width Chinese punctuation （），。、：「」 for Chinese text, but keep the original punctuation inside anything that stays English, and keep spaces around inline English words and numbers.`

phase('Translate')
const names = args.chunks
const done = await parallel(names.map((n) => () =>
  agent(`${RULES}\n\nTranslate chunk ${n}: read ${SITE}/chunks/en-${n}.json and write ${SITE}/chunks/zh-${n}.json.`,
    { label: `zh:${n}`, phase: 'Translate' })))
return { translated: done.filter(Boolean).length, of: names.length }
