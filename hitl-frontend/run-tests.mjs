import { spawnSync } from 'child_process';
import { writeFileSync } from 'fs';

const args = process.argv.slice(2);
const vitestArgs = ['--run', '--reporter=verbose', ...args];

const r = spawnSync(import.meta.dirname + '/node_modules/.bin/vitest.cmd', vitestArgs, {
  cwd: import.meta.dirname,
  encoding: 'utf8',
  timeout: 120000,
  env: { ...process.env, FORCE_COLOR: '0', NO_COLOR: '1' },
});

const output = [
  'EXIT: ' + r.status,
  'SIGNAL: ' + r.signal,
  'ERROR: ' + (r.error ? r.error.message : 'none'),
  '--- STDOUT ---',
  r.stdout || '(empty)',
  '--- STDERR ---',
  r.stderr || '(empty)',
].join('\n');

writeFileSync(import.meta.dirname + '/test-output.txt', output, 'utf8');
