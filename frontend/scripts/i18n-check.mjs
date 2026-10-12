// Lists English UI strings that have no Kiswahili entry in src/i18n.sw.ts.
//   node scripts/i18n-check.mjs          -> prints missing keys, exits 1 if any
// Strings are found from t("...") / tn(n, "one", "many") calls in src, plus the labels
// the backend sends (court levels, case types, delay reasons...) listed below.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../src/", import.meta.url));
const files = [];
(function walk(dir) {
  for (const f of readdirSync(dir)) {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) walk(p);
    else if (/\.tsx?$/.test(f) && !f.startsWith("i18n.sw")) files.push(p);
  }
})(root);

const keys = new Set();
const str = String.raw`"((?:[^"\\]|\\.)*)"`;
for (const f of files) {
  const src = readFileSync(f, "utf8");
  for (const m of src.matchAll(new RegExp(String.raw`\bt\(\s*` + str, "g"))) keys.add(JSON.parse(`"${m[1]}"`));
  for (const m of src.matchAll(new RegExp(String.raw`\bt\(\s*[^"()]*\?\s*` + str + String.raw`\s*:\s*` + str, "g"))) {
    keys.add(JSON.parse(`"${m[1]}"`)); keys.add(JSON.parse(`"${m[2]}"`));
  }
  for (const m of src.matchAll(new RegExp(String.raw`\btn\([^,]+,\s*` + str + String.raw`\s*,\s*` + str, "g"))) {
    keys.add(`{n} ${m[1]}`); keys.add(`{n} ${m[2]}`);
  }
}

// Labels from the backend and from lookup tables in the pages.
const dynamic = [
  "Primary", "District", "Resident Magistrate", "High Court", "Court of Appeal",
  "Criminal", "Civil", "Land", "Matrimonial", "Probate", "Labour", "Commercial", "Economic",
  "Homicide", "Sexual offence", "Robbery / violence", "Property / theft", "Drugs", "Corruption / economic", "Other", "Not criminal",
  "High Court Land Division", "High Court Labour Division", "High Court Commercial Division",
  "High Court Corruption and Economic Crimes Division", "High Court sub-registry",
  "High", "Medium", "Low", "Pending", "Disposed", "pending", "approved", "overridden", "proposed",
  "approve risk", "override risk", "approve", "edit", "remove", "acknowledge",
  "Mon", "Tue", "Wed", "Thu", "Fri", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
  "Court Clerk", "Court Registrar", "Magistrate / Judge", "Court Management", "Administrator",
  "Court Clerk (demo)", "Court Registrar (demo)", "Magistrate (demo)", "Court Management (demo)", "System Admin (demo)",
  "Court-controllable", "Advocate-requested postponement", "State attorney / prosecution delay",
  "Pending forensic / expert report", "Witness did not attend", "Awaiting record of proceedings",
  "State attorney / prosecution delay (incl. investigation)", "Awaiting record of proceedings (appeals)",
  "Court-side (magistrate unavailable, list overrun)", "Court-side", "adjourned", "proceeded", "disposed",
  "Police (investigation) and National Prosecutions Service", "Government Chemist Laboratory Authority",
  "Police (summons) and the parties", "Advocates (Tanganyika Law Society)", "Court registry (record of proceedings)",
  "Court (in-charge judge or magistrate)",
  "Legally represented", "Unrepresented", "Advocate postponement active", "No advocate postponement",
  "Prosecution delay active", "No prosecution delay", "Forensic report pending", "No forensic report pending",
  "Witnesses attending", "Record of proceedings ready", "Already past disposition target", "No single dominant factor",
  "Main", "Oversight", "Administration", "Dashboard", "Case data entry", "My schedule", "Review queue", "Cause list",
  "Case list", "Criminal sessions", "Escalations", "Reports", "Fairness audit", "Settings", "Committee agenda",
  "Date passed, no hearing recorded", "Ask the clerk to record what happened, or fix a new date.",
  "No next date fixed", "These cases will be offered free slots on next week's list.",
  "High risk, next date far away", "Consider bringing these forward.",
  "Same external delay three times in a row", "Raise with the body named, through the case-flow committee.",
  "Accused in remand more than 6 months", "Priority for listing and for the committee.",
  "Good morning", "Good afternoon", "Good evening", "Yes", "No",
];
for (const d of dynamic) keys.add(d);

const sw = readFileSync(join(root, "i18n.sw.ts"), "utf8");
const have = new Set([...sw.matchAll(new RegExp(String.raw`(?:^|[{,])\s*` + str + String.raw`\s*:`, "gm"))].map((m) => JSON.parse(`"${m[1]}"`)));
const missing = [...keys].filter((k) => !have.has(k)).sort();
const unused = [...have].filter((k) => !keys.has(k)).sort();
if (process.argv.includes("--list")) for (const k of [...keys].sort()) console.log(JSON.stringify(k));
console.log(`${keys.size} strings, ${have.size} translated, ${missing.length} missing`);
for (const k of missing) console.log("  missing:", JSON.stringify(k));
if (unused.length) console.log(`${unused.length} entries not used (fine to keep)`);
process.exit(missing.length ? 1 : 0);
