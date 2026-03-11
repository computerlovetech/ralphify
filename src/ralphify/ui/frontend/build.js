import * as esbuild from 'esbuild';

const watch = process.argv.includes('--watch');

const options = {
  entryPoints: ['src/app.js'],
  bundle: true,
  outfile: '../static/dashboard.js',
  format: 'esm',
  minify: !watch,
  sourcemap: watch,
  target: 'es2020',
  jsxFactory: 'h',
  jsxFragment: 'Fragment',
  external: [],
};

if (watch) {
  const ctx = await esbuild.context(options);
  await ctx.watch();
  console.log('Watching for changes...');
} else {
  await esbuild.build(options);
  console.log('Build complete.');
}
