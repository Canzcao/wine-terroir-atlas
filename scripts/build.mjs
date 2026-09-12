import fs from 'node:fs/promises';import path from 'node:path';import {build} from 'esbuild';
await fs.mkdir('work',{recursive:true});await fs.copyFile('node_modules/exceljs/dist/exceljs.min.js','public/assets/exceljs.min.js');
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json','.geojson':'application/geo+json','.svg':'image/svg+xml','.png':'image/png'};const assets={};
async function walk(dir){for(const f of await fs.readdir(dir,{withFileTypes:true})){const p=path.join(dir,f.name);if(f.isDirectory())await walk(p);else assets['/'+p.slice(7)]={type:types[path.extname(p)]||'text/plain',body:(await fs.readFile(p)).toString('base64')}}}await walk('public');
await fs.writeFile('work/assets.js','export default '+JSON.stringify(assets));
await fs.rm('dist',{recursive:true,force:true});await fs.mkdir('dist/server',{recursive:true});
await build({entryPoints:['worker/index.js'],outfile:'dist/server/index.js',bundle:true,format:'esm',platform:'browser',target:'es2022',minify:true});console.log('Built Worker and',Object.keys(assets).length,'embedded assets');
