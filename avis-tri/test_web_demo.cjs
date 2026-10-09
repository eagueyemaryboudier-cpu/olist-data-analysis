const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map();const el=id=>{if(!elements.has(id))elements.set(id,{value:'',checked:false,innerHTML:'',textContent:'',addEventListener(){},click(){}});return elements.get(id)};
const data=JSON.parse(fs.readFileSync('../docs/data.json','utf8'));let blob;
const context=vm.createContext({document:{getElementById:el},fetch:async()=>({ok:true,json:async()=>data}),Blob,URL:{createObjectURL:b=>{blob=b;return 'blob:test'},revokeObjectURL(){}}});
vm.runInContext(fs.readFileSync('../docs/demo.js','utf8').replace(/init\(\);\s*$/,''),context);
context.testData=data.rows;vm.runInContext('all=testData;apply()',context);
assert.equal(el('count').textContent,'36');
el('language').value='fr';el('sentiment').value='Négatif';vm.runInContext('apply()',context);
assert.equal(el('count').textContent,'5');
assert.match(el('sentimentChart').innerHTML,/5 · 100 %/);
el('json').onclick();
(async()=>{
const rows=JSON.parse(await blob.text());assert.equal(rows.length,5);assert(rows.every(x=>x.langue==='fr'&&x.sentiment==='Négatif'));assert(rows.every(x=>x.source.includes('fictif')));
el('reset').onclick();el('search').value='IMPOSSIBLE_NO_MATCH';vm.runInContext('apply()',context);assert.equal(el('count').textContent,'0');assert.equal(el('csv').disabled,true);assert.doesNotMatch(el('sentimentChart').innerHTML,/NaN|Infinity/);
el('reset').onclick();assert.match(el('themeChart').innerHTML,/17 · 47,2 %/);el('next').onclick();assert.equal(el('page').textContent,'Page 2 / 3');el('previous').onclick();assert.equal(el('page').textContent,'Page 1 / 3');
const dangerous=vm.runInContext(`csv([{texte:'=1+1',themes:'x'}])`,context);assert(dangerous.includes("'=1+1"));console.log('OK : 36 exemples, filtres, parts du total, pagination, export fidèle et aucun résultat.');
})().catch(e=>{console.error(e);process.exitCode=1});
