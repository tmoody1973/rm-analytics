/**
 * Radio Milwaukee — "Sync to Neon"
 *
 * Pushes the finance KPI sheet into the Neon warehouse with NO Coupler account slot.
 * It reads the FIRST tab (the "financial" KPI dashboard) using DISPLAYED values — so
 * "36.67%", "1,489,865.75", and "(71,757.38)" arrive exactly as shown — and POSTs:
 *
 *     { dataset: "finance_kpi", rows: [ { <header>: <value>, ... }, ... ] }
 *
 * to the rm-data-loader service, which unpivots + upserts into finance.fact_kpi_monthly.
 *
 * ONE-TIME SETUP
 *   1. Extensions -> Apps Script. Paste this file. Save.
 *   2. Project Settings -> Script properties, add two rows:
 *        ENDPOINT = https://rm-data-loader.fly.dev/webhook/sheet
 *        SECRET   = <the SHEET_SYNC_SECRET value set as a Fly.io secret>
 *   3. Reload the sheet. Menu: "Radio Milwaukee" -> "Sync finance to Neon".
 *   (Optional) Triggers -> add a daily time-driven trigger for `syncFinance`.
 */

var DATASET = 'finance_kpi';

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Radio Milwaukee')
    .addItem('Sync finance to Neon', 'syncFinance')
    .addToUi();
}

function syncFinance() {
  // The financial KPI dashboard is the first tab.
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
  var rows = sheetToObjects(sheet);
  var result = postToNeon(DATASET, rows);
  try {
    SpreadsheetApp.getUi().alert('Sync finance -> Neon\n\n' + result);
  } catch (e) {
    // No UI is available when this runs from a time-driven trigger; ignore.
  }
  return result;
}

/** Header-keyed row objects from a sheet, using displayed (formatted) values. */
function sheetToObjects(sheet) {
  var values = sheet.getDataRange().getDisplayValues();
  if (values.length < 2) return [];
  var headers = values[0].map(String);
  var out = [];
  for (var i = 1; i < values.length; i++) {
    var r = values[i];
    var hasData = r.some(function (c) { return String(c).trim() !== ''; });
    if (!hasData) continue; // skip fully-blank rows
    var obj = {};
    for (var j = 0; j < headers.length; j++) obj[headers[j]] = r[j];
    out.push(obj);
  }
  return out;
}

function postToNeon(dataset, rows) {
  var props = PropertiesService.getScriptProperties();
  var resp = UrlFetchApp.fetch(props.getProperty('ENDPOINT'), {
    method: 'post',
    contentType: 'application/json',
    headers: { 'X-RM-Sheet-Secret': props.getProperty('SECRET') },
    payload: JSON.stringify({ dataset: dataset, rows: rows }),
    muteHttpExceptions: true,
  });
  return resp.getResponseCode() + ' ' + resp.getContentText();
}
