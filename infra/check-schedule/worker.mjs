// The scheduler only dispatches the existing protected GitHub runner.
// It never receives a database credential, monitor URL, or browser session.
const REPOSITORY = 'fmvini/Vigil';
const WORKFLOW = 'free-checks.yml';
const ENDPOINT = `https://api.github.com/repos/${REPOSITORY}/actions/workflows/${WORKFLOW}/dispatches`;
const API_VERSION = '2026-03-10';

export async function dispatchChecks(env, fetcher = (url, options) => globalThis.fetch(url, options)) {
  if (env.VIGIL_SCHEDULE_ENABLED !== 'true') return { status: 'disabled' };
  const token = env.VIGIL_GITHUB_ACTIONS_TOKEN;
  if (typeof token !== 'string' || !/^github_pat_[A-Za-z0-9_]{30,245}$/.test(token)) {
    throw new Error('schedule_token_missing_or_invalid');
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);
  const startedAt = Date.now();
  let stage = 'request';
  let httpStatus = null;
  try {
    const response = await fetcher(ENDPOINT, {
      method: 'POST',
      // workerd only implements follow/manual. Reject every non-200 below;
      // never follow Location or send the token to another destination.
      redirect: 'manual',
      signal: controller.signal,
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        'User-Agent': 'Vigil-check-schedule',
        'X-GitHub-Api-Version': API_VERSION,
      },
      body: JSON.stringify({ ref: 'main' }),
    });
    httpStatus = response.status;
    stage = 'receipt';
    // API 2026-03-10 returns the run ID. Acceptance does not prove a check.
    if (response.status !== 200) throw new Error(`schedule_dispatch_http_${response.status}`);
    const data = await response.json();
    if (!Number.isSafeInteger(data.workflow_run_id) || data.workflow_run_id < 1) {
      throw new Error('schedule_dispatch_receipt_invalid');
    }
    return {
      status: 'dispatch_accepted',
      workflow_run_id: data.workflow_run_id,
      html_url: `https://github.com/${REPOSITORY}/actions/runs/${data.workflow_run_id}`,
    };
  } catch (error) {
    const errorName = ['Error', 'TypeError', 'SyntaxError', 'AbortError'].includes(error?.name)
      ? error.name : 'UnknownError';
    console.error(JSON.stringify({ status: 'dispatch_failed', stage, error_name: errorName,
      aborted: controller.signal.aborted, elapsed_ms: Date.now() - startedAt, http_status: httpStatus }));
    // Do not expose provider response bodies, request headers, or fetch errors.
    if (error instanceof Error && /^schedule_dispatch_(?:http_\d{3}|receipt_invalid)$/.test(error.message)) {
      throw error;
    }
    throw new Error('schedule_dispatch_unavailable');
  } finally {
    clearTimeout(timer);
  }
}

export default {
  async scheduled(controller, env) {
    const receipt = await dispatchChecks(env);
    console.log(JSON.stringify({ ...receipt, scheduled_at: controller.scheduledTime }));
  },
  // Even if an operator accidentally enables a route, HTTP cannot dispatch.
  fetch() {
    return new Response('Not found', { status: 404 });
  },
};
