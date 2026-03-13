import fs from 'node:fs';
import Ajv from 'ajv';
import addFormats from 'ajv-formats';

const schema = JSON.parse(fs.readFileSync('data/schema.json', 'utf8'));
const data = JSON.parse(fs.readFileSync('data/map_data.json', 'utf8'));

const ajv = new Ajv({ allErrors: true, strict: false });
addFormats(ajv);

const validate = ajv.compile(schema);
const ok = validate(data);

if (!ok) {
  console.error('❌ map_data.json failed schema validation:');
  console.error(validate.errors);
  process.exit(1);
}

// Extra check: edges reference existing node ids
const ids = new Set((data.nodes || []).map((n) => n.id));
const missing = [];
for (const e of (data.edges || [])) {
  if (!ids.has(e.from)) missing.push({ edge: e.id, missing: e.from });
  if (!ids.has(e.to)) missing.push({ edge: e.id, missing: e.to });
}

if (missing.length) {
  console.error('❌ Edges reference missing node ids:', missing);
  process.exit(1);
}

console.log('✅ map_data.json is valid.');
