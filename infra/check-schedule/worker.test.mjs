import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import worker, { dispatchChecks } from './worker.mjs';

const token = `github_pat_${'a'.repeat(80)}`;
const env = { VIGIL_SCHEDULE_ENABLED: 'true', VIGIL_GITHUB_ACTIONS_TOKEN: token };

test('disabled schedules never send credentials or dispatch', async () => {
  for (const enabled of [undefined, false, true, 'false', 'TRUE', '']) {
    assert.deepEqual(await dispatchChecks({ ...env, VIGIL_SCHEDULE_ENABLED: enabled }, () => {
      assert.fail('disabled schedule dispatched');
    }), { status: 'disabled' });
  }
});

test('acceptance is identified by run ID and is distinct from completion', async () => {
  let requests = 0;
  const receipt = await dispatchChecks(env, async (url, options) => {
    requests++;
    assert.equal(url, 'https://api.github.com/repos/fmvini/Vigil/actions/workflows/free-checks.yml/dispatches');
    assert.equal(options.method, 'POST');
    assert.equal(options.redirect, 'manual');
    assert.equal(options.headers.Authorization, `Bearer ${token}`);
    assert.equal(options.headers['X-GitHub-Api-Version'], '2026-03-10');
    assert.deepEqual(JSON.parse(options.body), { ref: 'main' });
    assert.equal(options.signal.aborted, false);
    return Response.json({ workflow_run_id: 123, html_url: 'https://untrusted.invalid/' });
  });
  assert.equal(requests, 1);
  assert.deepEqual(receipt, { status: 'dispatch_accepted', workflow_run_id: 123,
    html_url: 'https://github.com/fmvini/Vigil/actions/runs/123' });
  assert.equal(JSON.stringify(receipt).includes(token), false);
});

test('bad credentials are rejected before sending', async () => {
  for (const value of [undefined, '', 'ghp_classic_token', token + '\n', token + '\rHeader: injected']) {
    await assert.rejects(dispatchChecks({ ...env, VIGIL_GITHUB_ACTIONS_TOKEN: value }, () => {
      assert.fail('invalid secret sent');
    }), { message: 'schedule_token_missing_or_invalid' });
  }
});

test('default transport preserves the Workers global fetch receiver', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async function (url) {
      assert.equal(this, globalThis);
      assert.equal(url, 'https://api.github.com/repos/fmvini/Vigil/actions/workflows/free-checks.yml/dispatches');
      return Response.json({ workflow_run_id: 456 });
    };
    assert.equal((await dispatchChecks(env)).workflow_run_id, 456);
  } finally {
    globalThis.fetch = original;
  }
});

test('failed responses do not disclose bodies or retry dispatches', async () => {
  for (const status of [301, 302, 307, 308, 401, 403, 429, 500]) {
    let requests = 0;
    await assert.rejects(dispatchChecks(env, async (_url, options) => {
      requests++;
      assert.equal(options.redirect, 'manual');
      return new Response(`private ${token}`, { status,
        headers: { Location: 'https://untrusted.invalid/' } });
    }), { message: `schedule_dispatch_http_${status}` });
    assert.equal(requests, 1);
  }
  await assert.rejects(dispatchChecks(env, async () => new Response(null, { status: 204 })),
    { message: 'schedule_dispatch_http_204' });
});

test('network deadline aborts the dispatch without retrying or disclosing secrets', async () => {
  let requests = 0;
  await assert.rejects(dispatchChecks(env, async (_url, options) => {
    requests++;
    return new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new Error(`private ${token}`)), { once: true });
    });
  }), { message: 'schedule_dispatch_unavailable' });
  assert.equal(requests, 1);
});

test('invalid receipt and transport errors are sanitized', async () => {
  for (const id of [undefined, 0, -1, '123', 1.5, Number.MAX_SAFE_INTEGER + 1]) {
    await assert.rejects(dispatchChecks(env, async () => Response.json({ workflow_run_id: id })),
      { message: 'schedule_dispatch_receipt_invalid' });
  }
  await assert.rejects(dispatchChecks(env, async () => { throw new Error(`private ${token}`); }),
    { message: 'schedule_dispatch_unavailable' });
  await assert.rejects(dispatchChecks(env, async () => new Response('invalid json')),
    { message: 'schedule_dispatch_unavailable' });
});

test('HTTP entrypoint cannot trigger a run', async () => {
  for (const method of ['GET', 'POST']) {
    const response = await worker.fetch(new Request('https://example.com/', { method }), env);
    assert.equal(response.status, 404);
  }
});

test('diagnostics identify the failing phase without exposing transport details', async () => {
  const original = console.error;
  const records = [];
  try {
    console.error = value => records.push(JSON.parse(value));
    await assert.rejects(dispatchChecks(env, async () => { throw new TypeError(`private ${token}`); }),
      { message: 'schedule_dispatch_unavailable' });
    await assert.rejects(dispatchChecks(env, async () => new Response('invalid json')),
      { message: 'schedule_dispatch_unavailable' });
    assert.equal(records[0].stage, 'request');
    assert.equal(records[0].error_name, 'TypeError');
    assert.equal(records[0].http_status, null);
    assert.equal(records[1].stage, 'receipt');
    assert.equal(records[1].error_name, 'SyntaxError');
    assert.equal(records[1].http_status, 200);
    assert.equal(records[0].aborted, false);
    assert.equal(JSON.stringify(records).includes(token), false);
    assert.equal(JSON.stringify(records).includes('private'), false);
    assert.ok(records.every(r => Number.isFinite(r.elapsed_ms) && r.elapsed_ms >= 0));
  } finally {
    console.error = original;
  }
});

test('deployment is disabled by default, has no public route, and preserves 15min cron', () => {
  const config = JSON.parse(readFileSync(new URL('./wrangler.jsonc', import.meta.url), 'utf8'));
  assert.equal(config.vars.VIGIL_SCHEDULE_ENABLED, 'false');
  assert.equal(config.workers_dev, false);
  assert.equal(config.preview_urls, false);
  assert.equal(config.routes, undefined);
  assert.deepEqual(config.triggers.crons, ['2,17,32,47 * * * *']);
  assert.equal(JSON.stringify(config).includes('github_pat_'), false);
});
