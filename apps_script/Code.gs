/**
 * BuildNation Tender Watch: control panel + mailer.
 *
 * Paste this into Extensions → Apps Script of a Google Sheet owned by a BuildNation account.
 * It does three jobs, so the agent needs no mailbox password and managers need no code:
 *   1. Holds the settings the agent uses (services, keywords, recipients, thresholds): edited in the sheet.
 *   2. Sends the daily digest email from the sheet owner's account (MailApp).
 *   3. Logs every match in the "Opportunities" tab, where reviewers mark them Relevant / Not relevant.
 *      Those marks are sent back to the AI as examples, so it learns what BuildNation wants.
 *
 * Setup (once): run setup() from the editor, then Deploy → New deployment → Web app
 *   (Execute as: Me, Who has access: Anyone). See README "Step 3".
 */

const TABS = {
  guide: 'How to use',
  settings: 'Settings',
  services: 'Services',
  keywords: 'Keywords',
  log: 'Opportunities',
};
const LOG_HEADERS = ['Date found', 'Score', 'Title', 'Organisation', 'Country', 'Deadline', 'Link', 'Why (AI)', 'Portal', 'Your verdict', 'Notes', 'Key'];
const VERDICTS = ['', 'Relevant', 'Not relevant', 'Applying', 'Applied'];

// ---------------------------------------------------------------- web app (called by the agent)

function doPost(e) {
  try {
    const req = JSON.parse(e.postData.contents);
    if (req.token !== PropertiesService.getScriptProperties().getProperty('TOKEN')) {
      return json_({ ok: false, error: 'bad token' });
    }
    if (req.action === 'settings') return json_({ ok: true, settings: readSettings_() });
    if (req.action === 'send') return json_(sendDigest_(req));
    return json_({ ok: false, error: 'unknown action' });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

function doGet() {
  return ContentService.createTextOutput('BuildNation Tender Watch control panel is running.');
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

// ---------------------------------------------------------------- settings

function readSettings_() {
  const ss = SpreadsheetApp.getActive();

  const kv = {};
  ss.getSheetByName(TABS.settings).getDataRange().getValues().slice(1).forEach(r => {
    if (String(r[0]).trim()) kv[String(r[0]).trim()] = r[1];
  });

  const services = ss.getSheetByName(TABS.services).getDataRange().getValues().slice(1)
    .filter(r => String(r[0]).trim() && r[2] === true)
    .map(r => '- ' + String(r[0]).trim() + (String(r[1]).trim() ? ': ' + String(r[1]).trim() : ''));

  const kw = ss.getSheetByName(TABS.keywords).getDataRange().getValues().slice(1);
  const col = i => kw.map(r => String(r[i] || '').trim()).filter(Boolean);

  const profile = [String(kv.company_intro || '').trim(), 'Services offered or wanted:', services.join('\n'),
                   String(kv.delivery || '').trim()].filter(Boolean).join('\n');

  const sources = {};
  Object.keys(kv).filter(k => k.indexOf('portal_') === 0).forEach(k => { sources[k.slice(7)] = kv[k] === true; });

  return {
    company_profile: profile,
    include_keywords: col(0),
    exclude_keywords: col(1),
    exclude_notice_types: col(2),
    recipients: String(kv.recipients || '').split(/[,;\s]+/).filter(Boolean),
    min_score: Number(kv.min_score) || 6,
    lookback_days: Number(kv.lookback_days) || 2,
    send_when_empty: kv.send_when_empty !== false,
    sources: sources,
    feedback: readFeedback_(),
  };
}

/** Latest reviewer verdicts, sent to the AI as examples of what BuildNation does and does not want. */
function readFeedback_() {
  const rows = SpreadsheetApp.getActive().getSheetByName(TABS.log).getDataRange().getValues().slice(1);
  const out = [];
  for (let i = rows.length - 1; i >= 0 && out.length < 30; i--) {
    const verdict = String(rows[i][9]).trim();
    if (!verdict) continue;
    out.push({ title: String(rows[i][2]), organisation: String(rows[i][3]), verdict: verdict,
               relevant: verdict !== 'Not relevant', note: String(rows[i][10] || '') });
  }
  return out;
}

// ---------------------------------------------------------------- email + log

function sendDigest_(req) {
  const settings = readSettings_();
  const to = settings.recipients;
  if (!to.length) return { ok: false, error: 'no recipients in Settings tab' };
  MailApp.sendEmail({ to: to.join(','), subject: req.subject, htmlBody: req.html, body: req.text,
                      name: 'BuildNation Tender Watch' });

  const log = SpreadsheetApp.getActive().getSheetByName(TABS.log);
  const known = new Set(log.getDataRange().getValues().slice(1).map(r => r[11]));
  const rows = (req.matches || []).filter(m => !known.has(m.key)).map(m => [
    new Date(), m.score === null ? 'unscored' : m.score, m.title, m.org, m.country, m.deadline,
    m.url, m.reason, m.portal, '', '', m.key]);
  if (rows.length) {
    log.getRange(log.getLastRow() + 1, 1, rows.length, LOG_HEADERS.length).setValues(rows);
    log.getRange(2, 10, log.getLastRow() - 1, 1)
       .setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(VERDICTS, true).build());
  }
  return { ok: true, sent_to: to.length, logged: rows.length, quota_left: MailApp.getRemainingDailyQuota() };
}

// ---------------------------------------------------------------- one-time setup

function setup() {
  const ss = SpreadsheetApp.getActive();
  const props = PropertiesService.getScriptProperties();
  if (!props.getProperty('TOKEN')) props.setProperty('TOKEN', Utilities.getUuid() + Utilities.getUuid().slice(0, 8));

  tab_(ss, TABS.guide, [['BuildNation Tender Watch: control panel'], [''],
    ['Every morning the agent reads this sheet, checks 5 tender portals and emails matches to the recipients below.'],
    ['Change anything here; it applies from the next run. No code needed.'], [''],
    ['Settings: who gets the email, minimum AI score (0-10), which portals to check.'],
    ['Services: what BuildNation offers or wants to grow into. Tick "Active". The AI judges fit against this list.'],
    ['Keywords: a title must contain an Include word (and no Exclude word) to be considered at all.'],
    ['Opportunities: every match is logged here. Set "Your verdict" (Relevant / Not relevant): the AI learns from it.'],
    [''], ['Do not rename the tabs or the first column of Settings.']]);

  tab_(ss, TABS.settings, [['Setting', 'Value', 'What it does'],
    ['recipients', 'name@example.com', 'Who gets the digest. Separate several with commas.'],
    ['min_score', 6, 'AI score (0-10) needed to appear in the email. 7-8 = fewer, stronger leads.'],
    ['lookback_days', 2, 'Days of notices checked each run (overlap is fine: nothing is sent twice).'],
    ['send_when_empty', true, 'Send a short email even when nothing matched (proves the agent is alive).'],
    ['company_intro', 'BuildNation is a Bangladesh-based edtech company that designs and delivers training and learning solutions.', 'One or two sentences about the company, read by the AI.'],
    ['delivery', 'It can deliver remotely/online anywhere, or in person anywhere in Bangladesh.', 'Where BuildNation can work. Notices outside this are rejected.'],
    ['portal_undp', true, 'UNDP (Quantum) procurement notices'],
    ['portal_ungm', true, 'UN Global Marketplace'],
    ['portal_egp', true, 'Bangladesh e-GP'],
    ['portal_brac', true, 'BRAC e-Tender'],
    ['portal_smef', true, 'SME Foundation']]);
  checkboxes_(ss.getSheetByName(TABS.settings), ['send_when_empty', 'portal_']);

  tab_(ss, TABS.services, [['Service', 'Description (optional)', 'Active'],
    ['Learning management systems (LMS)', 'LMS and e-learning platforms: build, customise, host, support', true],
    ['Digital content & curriculum development', 'Courses, modules, e-learning content, training manuals', true],
    ['Capacity building programmes', 'Design and delivery of capacity-building for organisations and institutions', true],
    ['Vocational / TVET training', 'Technical and vocational skills, TVET institutions, trainer training', true],
    ['Professional & soft skills training', '', true],
    ['IT & digital skills training', 'Digital literacy, ICT skills', true],
    ['AI, coding & software development training', '', true],
    ['Leadership & management training', '', true],
    ['Education / training consultancy', 'Training needs assessments, programme design, evaluation of training', true],
    ['Workshop design & facilitation', '', true],
    ['Adjacent: edtech, digital transformation of training institutions, skills research', 'Nearby work BuildNation could grow into', true]]);
  const svc = ss.getSheetByName(TABS.services);
  svc.getRange(2, 3, svc.getMaxRows() - 1, 1).insertCheckboxes();

  const include = ['training', 'trainer', 'capacity building', 'capacity development', 'capacity strengthening', 'e-learning',
    'elearning', 'online learning', 'blended learning', 'LMS', 'learning management', 'learning platform', 'curriculum', 'course',
    'courseware', 'module', 'content development', 'TVET', 'vocational', 'skills', 'skill development', 'upskilling', 'reskilling',
    'digital literacy', 'digital skills', 'ICT', 'IT', 'software', 'AI', 'artificial intelligence', 'machine learning', 'coding',
    'programming', 'leadership', 'coaching', 'mentoring', 'facilitator', 'facilitation', 'workshop', 'bootcamp', 'education',
    'edtech', 'learning', 'consultancy', 'consultant', 'consulting firm', 'training needs assessment', 'institutional',
    'expression of interest', 'EOI', 'REOI', 'প্রশিক্ষণ', 'দক্ষতা', 'শিক্ষা'];
  const exclude = ['hotel', 'catering', 'venue', 'conference hall', 'vehicle', 'fuel', 'air ticket', 'air ticketing',
    'construction of', 'construction works', 'civil works', 'renovation', 'rehabilitation of', 'repair', 'maintenance works',
    'linen', 'medical', 'medicine', 'pharmaceutical', 'edible oil', 'spare parts', 'printing', 'transport of', 'overhauling',
    'engine', 'vertical extension', 'furniture'];
  const n = Math.max(include.length, exclude.length);
  const kwRows = [['Include (title must contain one)', 'Exclude (title must not contain)', 'Exclude notice types']];
  for (let i = 0; i < n; i++) kwRows.push([include[i] || '', exclude[i] || '', i === 0 ? 'Works' : '']);
  tab_(ss, TABS.keywords, kwRows);

  tab_(ss, TABS.log, [LOG_HEADERS]);
  ss.getSheetByName(TABS.log).hideColumns(12);

  const old = ss.getSheetByName('Sheet1');
  if (old && ss.getSheets().length > 1) ss.deleteSheet(old);

  const msg = 'Setup done.\n\nSecret token (put it in GitHub secret APPS_SCRIPT_TOKEN):\n' + props.getProperty('TOKEN') +
              '\n\nNext: Deploy → New deployment → Web app → Execute as: Me, Who has access: Anyone → copy the Web app URL into GitHub secret APPS_SCRIPT_URL.';
  Logger.log(msg);
  try { SpreadsheetApp.getUi().alert(msg); } catch (e) { /* run from editor without UI */ }
}

/** Create a tab with starting content, but never overwrite one that already exists. */
function tab_(ss, name, rows) {
  let sh = ss.getSheetByName(name);
  if (sh) return sh;
  sh = ss.insertSheet(name);
  const width = Math.max.apply(null, rows.map(r => r.length));
  sh.getRange(1, 1, rows.length, width).setValues(rows.map(r => r.concat(Array(width - r.length).fill(''))));
  sh.getRange(1, 1, 1, width).setFontWeight('bold').setBackground('#e8f0fe');
  sh.setFrozenRows(1);
  sh.autoResizeColumns(1, width);
  return sh;
}

function checkboxes_(sh, prefixes) {
  sh.getDataRange().getValues().forEach((r, i) => {
    if (prefixes.some(p => String(r[0]).indexOf(p) === 0)) sh.getRange(i + 1, 2).insertCheckboxes().setValue(r[1] === true);
  });
}
