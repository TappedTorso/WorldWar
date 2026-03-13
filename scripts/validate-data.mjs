import fs from "node:fs";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const schema = JSON.parse(fs.readFileSync("data/schema.json", "utf8"));
const data = JSON.parse(fs.readFileSync("data/map_data.json", "utf8"));

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);

const validate = ajv.compile(schema);
const ok = validate(data);

if (!ok) {
  console.error(validate.errors);
  process.exit(1);
}

console.log("✅ map_data.json is valid.");
