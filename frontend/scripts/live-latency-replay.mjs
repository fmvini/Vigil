// Offline audit of projected v3 evidence. Never opens a browser or contacts an API.
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { summary } from './live-latency-observer.mjs';

export const updateEvidenceLimit = 29;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const requestId = /^[A-Za-z0-9_.:-]{1,128}$/;
function require(condition, code) {
  if (!condition) { const error = new Error(code); error.code = code; throw error; }
}
function time(value) { return Number.isFinite(value) && value >= 0; }
function revision(value) { return Number.isSafeInteger(value) && value >= 0; }
function keys(object, expected) {
  return object !== null && typeof object === 'object' && !Array.isArray(object)
    && Object.keys(object).sort().join('|') === [...expected].sort().join('|');
}
function sameNumber(a, b) { return time(a) && time(b) && Math.abs(a - b) <= 0.000001; }

export function qaUpdateName(runId, ordinal) {
  require(typeof runId === 'string' && uuid.test(runId), 'EVIDENCE_RUN_INVALID');
  require(Number.isSafeInteger(ordinal) && ordinal >= 0 && ordinal <= updateEvidenceLimit, 'EVIDENCE_UPDATE_LIMIT');
  return `QA latency ${runId} #${String(ordinal).padStart(3, '0')}`;
}

function validateEvidence(evidence, { runId, projectId, ordinal, expectedRevision }) {
  require(keys(evidence, ['run_id', 'project_id', 'expected', 'cdp', 'browser']), 'EVIDENCE_FIELDS_INVALID');
  require(typeof projectId === 'string' && uuid.test(projectId) && evidence.run_id === runId && evidence.project_id === projectId, 'EVIDENCE_IDENTITY_MISMATCH');
  const name = qaUpdateName(runId, ordinal);
  require(ordinal > 0 && revision(expectedRevision), 'EVIDENCE_REVISION_INVALID');
  require(keys(evidence.expected, ['revision', 'name']) && evidence.expected.revision === expectedRevision && evidence.expected.name === name, 'EVIDENCE_EXPECTATION_MISMATCH');
  require(keys(evidence.cdp, ['sse', 'product_get']), 'EVIDENCE_CDP_FIELDS_INVALID');
  const { sse, product_get: get } = evidence.cdp;
  require(keys(sse, ['request_id', 'project_id', 'revision', 'timestamp_s']) && keys(get, ['request_id', 'project_id', 'revision', 'name', 'started_s', 'completed_s']), 'EVIDENCE_CDP_FIELDS_INVALID');
  require(typeof sse.request_id === 'string' && requestId.test(sse.request_id) && typeof get.request_id === 'string' && requestId.test(get.request_id) && sse.request_id !== get.request_id, 'EVIDENCE_REQUEST_ID_INVALID');
  require(sse.project_id === projectId && get.project_id === projectId && sse.revision === expectedRevision && get.revision === expectedRevision, 'EVIDENCE_REVISION_OR_PROJECT_MISMATCH');
  require(get.name === name, 'EVIDENCE_SNAPSHOT_NAME_MISMATCH');
  require(time(sse.timestamp_s) && time(get.started_s) && time(get.completed_s) && sse.timestamp_s <= get.started_s && get.started_s <= get.completed_s, 'EVIDENCE_CDP_ORDER_INVALID');
  const browser = evidence.browser;
  require(keys(browser, ['viewport', 'viewport_width', 'viewport_height', 'realm_time_origin_ms', 'patch_started_ms', 'dom_observed_ms', 'dom_name']), 'EVIDENCE_BROWSER_FIELDS_INVALID');
  const dimensions = browser.viewport === 'desktop' ? [1440, 900] : browser.viewport === 'mobile' ? [390, 844] : [];
  require(dimensions.length === 2 && browser.viewport_width === dimensions[0] && browser.viewport_height === dimensions[1] && time(browser.realm_time_origin_ms) && browser.realm_time_origin_ms > 0, 'EVIDENCE_BROWSER_SCOPE_INVALID');
  require(time(browser.patch_started_ms) && time(browser.dom_observed_ms) && browser.patch_started_ms <= browser.dom_observed_ms, 'EVIDENCE_BROWSER_ORDER_INVALID');
  require(browser.dom_name === name, 'EVIDENCE_DOM_NAME_MISMATCH');
}

export function buildUpdateEvidence({ runId, projectId, ordinal, expectedRevision, signal, snapshot, browser }) {
  // Projection, never object spreads or raw payload/body/header copies. Unexpected names
  // fail before serialization; failure reports contain a static code and evidence:null.
  const evidence = {
    run_id: runId, project_id: projectId,
    expected: { revision: expectedRevision, name: qaUpdateName(runId, ordinal) },
    cdp: {
      sse: { request_id: signal.request_id, project_id: signal.project_id, revision: signal.revision, timestamp_s: signal.timestamp },
      product_get: { request_id: snapshot.request_id, project_id: snapshot.project_id, revision: snapshot.revision, name: snapshot.name, started_s: snapshot.request_timestamp, completed_s: snapshot.completed_timestamp },
    },
    browser: { viewport: browser.viewport, viewport_width: browser.viewport_width, viewport_height: browser.viewport_height, realm_time_origin_ms: browser.realm_time_origin_ms, patch_started_ms: browser.patch_started_ms, dom_observed_ms: browser.dom_observed_ms, dom_name: browser.dom_name },
  };
  validateEvidence(evidence, { runId, projectId, ordinal, expectedRevision });
  return evidence;
}

export function replayLatencyReport(report) {
  if (report?.report_version !== 3) return { result: 'unsupported_report_version', code: 'UNSUPPORTED_REPORT_VERSION' };
  try {
    require(report.result === 'passed', 'REPORT_NOT_PASSED');
    require(typeof report.run_id === 'string' && uuid.test(report.run_id) && typeof report.identities?.project_id === 'string' && uuid.test(report.identities.project_id) && typeof report.identities.owner_id === 'string' && uuid.test(report.identities.owner_id), 'REPORT_IDENTITY_INVALID');
    const initialRevision = report.identities.initial_project_revision;
    require(revision(initialRevision), 'REPORT_INITIAL_REVISION_INVALID');
    require(Array.isArray(report.updates) && report.updates.length === updateEvidenceLimit, 'REPORT_UPDATE_COUNT_INVALID');
    require(Array.isArray(report.rest) && report.rest.length === 264, 'REPORT_REST_COUNT_INVALID');
    require(Array.isArray(report.errors) && report.errors.length === 0 && Array.isArray(report.network?.unexpected_statuses) && report.network.unexpected_statuses.length === 0, 'REPORT_ERRORS_PRESENT');
    const cleanup = report.cleanup;
    require(cleanup?.disposition === 'confirmed_api_scope' && cleanup.project_archive === 'confirmed' && cleanup.session_logout === 'confirmed' && cleanup.old_token_revocation === 'verified' && Array.isArray(cleanup.unknown_commit_possible) && cleanup.unknown_commit_possible.length === 0 && Array.isArray(cleanup.guards) && cleanup.guards.length >= 3 && cleanup.guards.every(guard => guard.status === 'passed'), 'REPORT_CLEANUP_NOT_CONFIRMED');
    require(['current_session_owner_and_csrf', 'singleton_project_id_slug_marker_current_name_revision_private_and_zero_monitors', 'captured_project_404_and_authenticated_list_empty'].every(name => cleanup.guards.some(guard => guard.guard === name && guard.status === 'passed')), 'REPORT_CLEANUP_GUARDS_MISSING');
    require(report.external_checks_executed === false && report.shared_gates_modified === false, 'REPORT_SCOPE_INVALID');
    const usedRequests = new Set();
    const streams = new Set();
    for (const [index, sample] of report.updates.entries()) {
      const desktop = index < 15;
      const warmup = index < 2 || (index >= 15 && index < 17);
      require(sample.ordinal === index + 1 && sample.viewport === (desktop ? 'desktop' : 'mobile') && sample.warmup === warmup, 'REPORT_UPDATE_PLAN_INVALID');
      require(sample.revision === initialRevision + index + 1 && sample.status === 200 && sample.success === true && sample.native_sse_revision_match === true && sample.product_rest_revision_match === true && sample.product_get_started_after_sse === true && typeof sample.periodic_overlap === 'boolean' && time(sample.patch_rtt_ms), 'REPORT_UPDATE_STATUS_OR_REVISION_INVALID');
      validateEvidence(sample.evidence, { runId: report.run_id, projectId: report.identities.project_id, ordinal: sample.ordinal, expectedRevision: sample.revision });
      const { cdp, browser } = sample.evidence;
      require(browser.viewport === sample.viewport, 'REPORT_BROWSER_SCOPE_MISMATCH');
      require(!usedRequests.has(cdp.product_get.request_id), 'REPORT_GET_REQUEST_REUSED');
      usedRequests.add(cdp.product_get.request_id);
      streams.add(cdp.sse.request_id);
      require(sameNumber(sample.sse_to_product_get_ms, (cdp.product_get.started_s - cdp.sse.timestamp_s) * 1000) && sameNumber(sample.request_start_to_dom_ms, browser.dom_observed_ms - browser.patch_started_ms), 'REPORT_EVIDENCE_DELTA_MISMATCH');
      if (index > 0) {
        const previous = report.updates[index - 1].evidence;
        require(browser.realm_time_origin_ms === previous.browser.realm_time_origin_ms, 'REPORT_BROWSER_REALM_CHANGED');
        require(cdp.sse.timestamp_s >= previous.cdp.sse.timestamp_s && browser.patch_started_ms >= previous.browser.dom_observed_ms, 'REPORT_UPDATE_ORDER_INVALID');
      }
    }
    require([...streams].every(id => !usedRequests.has(id)), 'REPORT_STREAM_GET_ID_COLLISION');
    const rest = report.rest.filter(sample => sample.warmup === false);
    const updates = report.updates.filter(sample => !sample.warmup);
    require(rest.length === 240 && report.rest.every(sample => typeof sample.warmup === 'boolean' && sample.status === 200 && sample.success === true && time(sample.elapsed_ms)), 'REPORT_REST_SAMPLES_INVALID');
    const byRoute = {};
    for (const route of ['projects', 'monitors', 'metrics', 'incidents']) {
      const measured = rest.filter(sample => sample.route === route);
      require(measured.length === 60, 'REPORT_REST_PLAN_INVALID');
      byRoute[route] = summary(measured.map(sample => sample.elapsed_ms), 60, 0);
      byRoute[route].by_viewport = {};
      for (const viewport of ['desktop', 'mobile']) {
        const subset = measured.filter(sample => sample.viewport === viewport);
        const warmups = report.rest.filter(sample => sample.route === route && sample.viewport === viewport && sample.warmup);
        require(subset.length === 30 && warmups.length === 3 && subset.every((sample, i) => sample.ordinal === i + 1) && warmups.every((sample, i) => sample.ordinal === i + 1), 'REPORT_REST_PLAN_INVALID');
        byRoute[route].by_viewport[viewport] = summary(subset.map(sample => sample.elapsed_ms), 30, 0);
      }
    }
    const ordered = updates.filter(sample => !sample.periodic_overlap);
    const recomputed = {
      rest_by_route: byRoute,
      rest_pooled_mixed_routes: summary(rest.map(sample => sample.elapsed_ms), 240, 0),
      patch_rtt: summary(updates.map(sample => sample.patch_rtt_ms), 25, 0),
      request_start_to_dom_upper_bound: summary(updates.map(sample => sample.request_start_to_dom_ms), 25, 0),
      sse_ordered_without_observed_periodic_overlap: summary(ordered.map(sample => sample.request_start_to_dom_ms), ordered.length, 0),
      native_sse_to_product_get: summary(updates.map(sample => sample.sse_to_product_get_ms), 25, 0),
      ui_by_viewport: Object.fromEntries(['desktop', 'mobile'].map(viewport => {
        const subset = updates.filter(sample => sample.viewport === viewport);
        return [viewport, summary(subset.map(sample => sample.request_start_to_dom_ms), subset.length, 0)];
      })),
      actual_counts: { rest_measured: 240, rest_warmup: 24, updates_measured: 25, updates_warmup: 4 },
      all_created_resources: { synthetic_owners: 1, captured_projects: 1, monitors_created_by_tooling: 0, external_checks_executed_by_tooling: 0 },
    };
    // Known v2 summaries remain auditable; additive metadata is not copied or echoed.
    function equivalent(a, b) {
      if (a !== null && typeof a === 'object' && b !== null && typeof b === 'object') return Object.keys(b).every(key => Object.hasOwn(a, key) && equivalent(a[key], b[key]));
      return a === b;
    }
    require(equivalent(report.summary, recomputed), 'REPORT_SUMMARY_MISMATCH');
    return { result: 'passed_replay', report_version: 3, run_id: report.run_id, updates_verified: 29, measured_updates: 25, measured_rest: 240 };
  } catch (error) {
    return { result: 'failed_replay', code: error.code ?? 'REPORT_INVALID' };
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  let outcome;
  try {
    require(process.argv.length === 3, 'REPLAY_REPORT_PATH_REQUIRED');
    outcome = replayLatencyReport(JSON.parse(await readFile(process.argv[2], 'utf8')));
  } catch { outcome = { result: 'failed_replay', code: 'REPLAY_INPUT_INVALID' }; }
  console.log(JSON.stringify(outcome));
  if (outcome.result !== 'passed_replay') process.exitCode = 1;
}
