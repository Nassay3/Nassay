import { spawn, spawnSync } from 'node:child_process';

const pnpmCli = process.env.npm_execpath;
if (!pnpmCli) {
  throw new Error('Run this command through pnpm: pnpm dev');
}

function run(filter, env) {
  return spawn(
    process.execPath,
    [pnpmCli, '--filter', filter, 'run', 'dev'],
    {
      env: { ...process.env, ...env },
      stdio: 'inherit',
      windowsHide: true,
    },
  );
}

const api = run('@workspace/api-server', { PORT: '5000' });
const web = run('@workspace/trading-terminal', {
  PORT: '5173',
  BASE_PATH: '/',
  API_ORIGIN: 'http://127.0.0.1:5000',
});

const children = [api, web];
let stopping = false;

function stop(exitCode = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (!child.pid) continue;
    if (process.platform === 'win32') {
      spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], {
        stdio: 'ignore',
        windowsHide: true,
      });
    } else {
      child.kill('SIGTERM');
    }
  }
  process.exitCode = exitCode;
}

for (const child of children) {
  child.on('exit', (code) => {
    if (!stopping && code) stop(code);
  });
}

process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
