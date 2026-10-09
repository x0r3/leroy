"""Prepare a separate upstream test proposal; never modify the frozen Graphato checkout."""

import difflib
import hashlib
import json
import subprocess

from nas_ssh import ROOT

COMMIT = '0ad540dd578033d45e4d0c25d89fbe57b32102a4'
CHECKOUT = ROOT / '.sources/frozen-master/graphato-0ad540dd5780'
PROPOSED_COMMAND = '''async function nativeCommand(command, args = {}, options = {}) {
  const deadline = Date.now() + 90_000;
  const body = JSON.stringify({ command, args, clientId: 'web-open-fixture', requestId: randomUUID() });
  for (let attempt = 0; ; attempt++) {
    const response = await fetch(`${fixture.apiBase}/api/v1/commands`, { method: 'POST', redirect: 'error',
      headers: { ...(fixture.contractHeaders ?? apiContractHeaders), Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body, signal: AbortSignal.timeout(Math.max(1, deadline - Date.now())) });
    const value = await response.json();
    if (response.status === 429 && value.error?.kind === 'serverRateLimited'
        && attempt < (options.rateLimitRetries ?? 0)) {
      const retryAfter = response.headers.get('Retry-After');
      const seconds = Number(retryAfter);
      if (Number.isInteger(seconds) && seconds >= 1 && seconds <= 60
          && seconds === value.error.retryAfterSeconds && Date.now() + seconds * 1000 < deadline) {
        options.onRateLimit?.({ kind: value.error.kind, retryAfterSeconds: seconds, retryAfter });
        await delay(seconds * 1000);
        continue;
      }
    }
    if (response.status !== 200 || value.error) throw acceptanceFailure(value.error ?? new Error(`HTTP ${response.status}`), { command, secrets });
    return value.result;
  }
}'''


def blob(path):
    return subprocess.check_output(['git', 'show', COMMIT + ':' + path], cwd=CHECKOUT).decode('utf-8')


def main():
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=CHECKOUT, text=True).strip() == COMMIT
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=CHECKOUT)
    folder = ROOT / '.local/graphato-native-rate-proposal'
    assert not folder.exists()
    folder.mkdir()
    changes = {}
    path = 'apps/desktop/e2e-web/open-runner.mjs'
    original = blob(path)
    start = original.index('async function nativeCommand(')
    end = original.index('\n}', start) + 2
    original_command = original[start:end]
    changes[path] = original, original[:start] + PROPOSED_COMMAND + original[end:]
    (folder / 'original-command.txt').write_text(original_command, encoding='utf-8')
    (folder / 'proposed-command.txt').write_text(PROPOSED_COMMAND, encoding='utf-8')
    path = 'apps/desktop/e2e-web/followup-cases.mjs'
    original = blob(path)
    marker = "    for (let index = 0; index < 120; index++) {\n      await nativeCommand('sendSessionPrompt', { req: { sessionId: h.session.id, prompt: `SOAK_HISTORY_${index}` } });"
    assert original.count(marker) == 1
    replacement = """    const nativeRateLimits = [];
    const sendOptions = { rateLimitRetries: 2, onRateLimit: response => {
      nativeRateLimits.push(response);
      assert.ok(nativeRateLimits.length < 12, 'Sustained prompt throttling is not a successful soak');
    } };
    for (let index = 0; index < 120; index++) {
      await nativeCommand('sendSessionPrompt', { req: { sessionId: h.session.id, prompt: `SOAK_HISTORY_${index}` } }, sendOptions);"""
    proposed = original.replace(marker, replacement)
    proposed = proposed.replace('durationSeconds: (Date.now() - started) / 1000, failedResponses, statuses,',
                                'durationSeconds: (Date.now() - started) / 1000, failedResponses, statuses, nativeRateLimits: nativeRateLimits.length,')
    changes[path] = original, proposed
    patch = ''.join(''.join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                              fromfile='a/' + path, tofile='b/' + path))
                    for path, (before, after) in changes.items())
    destination = ROOT / 'docs/upstream-patches/graphato-soak-rate-handling-proposal.patch'
    assert not destination.exists()
    destination.write_text(patch, encoding='utf-8', newline='\n')
    for path, (_, value) in changes.items():
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding='utf-8', newline='\n')
    result = {'base_commit': COMMIT, 'proposal_patch_sha256': hashlib.sha256(patch.encode()).hexdigest(),
              'frozen_checkout_modified': False, 'applied_to_nas_acceptance': False,
              'application_runtime_or_rate_limits_changed': False,
              'original_soak_cases_tabs_prompts_duration_and_assertions_retained': True,
              'new_assertion': 'At most eleven native rate-limit retries across 120 prompts; at most two per prompt',
              'scope': 'Separate upstream test proposal; no replacement of original acceptance results',
              'production_replacement_ready': False}
    (folder / 'proposal.json').write_text(json.dumps(result, indent=2) + '\n')
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=CHECKOUT)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
