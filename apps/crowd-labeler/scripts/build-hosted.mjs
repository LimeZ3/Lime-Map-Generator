import { build as viteBuild } from 'vite';
import { build as bundle } from 'esbuild';
import { mkdir, copyFile } from 'node:fs/promises';
await viteBuild({ publicDir: false, define: { 'import.meta.env.VITE_HOSTED': JSON.stringify('true') }, build: { outDir: 'dist/client', emptyOutDir: true } });
await copyFile('public/favicon.svg', 'dist/client/favicon.svg');
await bundle({ entryPoints: ['server/worker.ts'], outfile: 'dist/server/index.js', bundle: true, format: 'esm', platform: 'browser', target: 'es2022' });
await mkdir('dist/.openai', { recursive: true });
await copyFile('.openai/hosting.json', 'dist/.openai/hosting.json');
