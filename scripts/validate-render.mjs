// scripts/validate-render.mjs
import fs from 'node:fs';

// ECharts world.js country name list (the ones you actually use)
const ECHARTS_NAMES = new Set([
  "United States of America", "Russia", "China", "Iran", "Israel",
  "Ukraine", "Turkey", "Syria", "Lebanon", "Yemen", "Iraq", "Sudan",
  "Ethiopia", "Chad", "Egypt", "Germany", "Poland", "France",
  "United Kingdom", "Spain", "Czech Rep.", "North Korea", "India",
  "Pakistan", "Myanmar", "Taiwan", "Philippines", "Vietnam",
  "Venezuela", "Bahrain", "Kuwait", "Qatar", "United Arab Emirates",
  "Oman", "Cyprus", "Palestine", "Belarus", "Romania", "Saudi Arabia", 
  "Japan", "South Korea", "S. Sudan", "Central African Rep.", "Burkina Faso", 
  "Mali", "Niger", "Benin", "Ghana", "Nigeria", "Cameroon", "Dem. Rep. Congo", 
  "Rwanda", "Mozambique", "Thailand", "Afghanistan", "Haiti", "Dominican Rep.", 
  "Ecuador", "Colombia", "Peru", "Cuba", "Eritrea", "Mexico", "Somalia"
  // add as you add nodes
]);

const VALID_CATEGORIES = new Set(['WAR','ALLY','POLICY','SPILLOVER','TENSION','INTERNAL']);
const FILL_TYPES = new Set(['state', 'territory']);

const data = JSON.parse(fs.readFileSync('data/map_data.json', 'utf8'));
const nodeIds = new Set(data.nodes.map(n => n.id));
let errors = 0;

for (const n of data.nodes) {
  // geoName contract
  if (FILL_TYPES.has(n.type) && n.geoName && !ECHARTS_NAMES.has(n.geoName)) {
    console.error(`❌ geoName mismatch: ${n.id} → "${n.geoName}" not in ECharts world map`);
    errors++;
  }
  // category existence
  if (!VALID_CATEGORIES.has(n.category)) {
    console.error(`❌ Unknown category: ${n.id} → "${n.category}"`);
    errors++;
  }
}

for (const e of data.edges) {
  // dangling edge references
  if (!nodeIds.has(e.from)) {
    console.error(`❌ Edge ${e.id}: from="${e.from}" not in nodes`);
    errors++;
  }
  if (!nodeIds.has(e.to)) {
    console.error(`❌ Edge ${e.id}: to="${e.to}" not in nodes`);
    errors++;
  }
}

if (errors === 0) console.log('✅ Render contracts valid.');
else process.exit(1);
