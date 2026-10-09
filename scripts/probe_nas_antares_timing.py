"""Measure frame callback delay around unchanged Antares authentication tests."""

import argparse
import hashlib
import json
import re
import subprocess
import sys

from nas_followup_support import inner, wait_production_build
from nas_gitea_target import idle
from nas_ssh import ROOT

COMMIT = "9f05b7f1aa56d709f269c37700a65785385a8391"
NAME = "tests/e2e/nas-auth-timing.spec.ts"
HOOKS = r'''

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const state = { frames: 0, maximumLag: 0, slow: [] as {lag: number; now: number; frame: number}[], sources: [] as string[], camera: [] as unknown[] };
    (window as unknown as { leroyTiming: typeof state }).leroyTiming = state;
    const original = window.requestAnimationFrame.bind(window);
    const ids = new WeakMap<FrameRequestCallback, number>();
    let sequence = 0;
    window.requestAnimationFrame = (callback) => {
      if (!ids.has(callback)) ids.set(callback, ++sequence);
      const id = ids.get(callback);
      const source = String(callback);
      if (!state.sources.includes(source) && state.sources.length < 12) state.sources.push(source.slice(0, 800));
      return original((frame) => {
      const now = performance.now();
      const lag = now - frame;
      state.frames++;
      state.maximumLag = Math.max(state.maximumLag, lag);
      if (lag > 100 && state.slow.length < 100) state.slow.push({lag, now, frame});
      if (source.includes('Math.min') && state.camera.length < 300) {
        const map = document.querySelector<HTMLElement>('.universe-canvas');
        state.camera.push({id, now, frame, scale: map?.dataset.mapScale, camera: map?.dataset.cameraState, width: map?.clientWidth, height: map?.clientHeight});
      }
      callback(frame);
      });
    };
  });
});

test.afterEach(async ({ page }, info) => {
  if (page.isClosed()) return;
  const timing = await page.evaluate(() => (window as unknown as {leroyTiming: unknown}).leroyTiming);
  console.log('LEROY_FRAME_TIMING ' + JSON.stringify({title: info.title, retry: info.retry, timing}));
});
'''

PROFILE_HOOKS = r'''
let profileSession: import('@playwright/test').CDPSession | undefined;
test.beforeEach(async ({ page }, info) => {
  if (!info.title.startsWith('authenticated command bridge')) return;
  profileSession = await page.context().newCDPSession(page);
  await profileSession.send('Performance.enable');
  await profileSession.send('Profiler.enable');
  await profileSession.send('Profiler.setSamplingInterval', { interval: 3000 });
  await profileSession.send('Profiler.start');
  await page.addInitScript(() => {
    const state = { longTasks: [] as {start: number; duration: number}[] };
    (window as unknown as { leroyLongTasks: typeof state }).leroyLongTasks = state;
    new PerformanceObserver(list => {
      for (const task of list.getEntries()) {
        if (state.longTasks.length < 500) state.longTasks.push({start: task.startTime, duration: task.duration});
      }
    }).observe({entryTypes: ['longtask']});
  });
});
test.afterEach(async ({ page }, info) => {
  if (!profileSession || page.isClosed()) return;
  const profile = await profileSession.send('Profiler.stop');
  const metrics = await profileSession.send('Performance.getMetrics');
  const tasks = await page.evaluate(() => (window as unknown as {leroyLongTasks: unknown}).leroyLongTasks);
  console.log('LEROY_CPU_PROFILE ' + JSON.stringify({retry: info.retry, profile, metrics, tasks}));
  await profileSession.detach();
  profileSession = undefined;
});
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", default="auth-clock")
    parser.add_argument("--candidate", default=COMMIT)
    parser.add_argument("--database-tmpfs", action="store_true")
    parser.add_argument("--profile", action="store_true", help="Record Chromium CPU samples and long tasks")
    args = parser.parse_args()
    assert re.fullmatch(r"[a-z0-9-]{1,24}", args.attempt)
    assert re.fullmatch(r"[a-f0-9]{40}", args.candidate)
    commit = args.candidate
    wait_production_build()
    idle()
    assert not json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}"))
    assert not any(name.startswith("antares-") for name in inner("ps", "--format", "{{.Names}}").splitlines())
    source = subprocess.check_output(
        ["git", "-C", str(ROOT / ".sources/antares-nas-validation"), "show", commit + ":tests/e2e/game-auth.spec.ts"],
        text=True, encoding="utf-8",
    )
    content = source + HOOKS + (PROFILE_HOOKS if args.profile else "")
    digest = hashlib.sha256(content.encode()).hexdigest()
    image = inner("inspect", "jenkins-parity", "--format", "{{.Image}}").strip()
    program = r'''
import hashlib,pathlib,subprocess
root=pathlib.Path('/var/jenkins_home/workspace/antares-ci')
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==COMMIT
path=root/NAME
if PHASE=='create':
 assert not path.exists()
 path.write_text(CONTENT)
else:
 assert hashlib.sha256(path.read_bytes()).hexdigest()==DIGEST
 path.unlink()
'''

    def file(phase):
        prefix = "\n".join(key + "=" + repr(value) for key, value in {
            "COMMIT": commit, "NAME": NAME, "CONTENT": content, "DIGEST": digest, "PHASE": phase,
        }.items()) + "\n"
        inner("run", "--rm", "--network", "none", "--memory", "128m", "--cpus", "0.5",
              "--volumes-from", "jenkins-parity", "--entrypoint", "python3", image, "-c", prefix + program)

    file("create")
    try:
        subprocess.run([
            sys.executable, "-X", "utf8", str(ROOT / "scripts/probe_nas_antares_browsers.py"),
            "--candidate", commit, "--attempt", args.attempt, "--test-file", NAME,
            "--project", "game-chromium", "--timeout-seconds", "480",
            *(["--database-tmpfs"] if args.database_tmpfs else []),
        ], check=True)
    finally:
        file("remove")


if __name__ == "__main__":
    main()
