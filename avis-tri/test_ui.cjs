// Test des filtres et des fichiers exportés avec un DOM simulé, sans navigateur.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {value:'', checked:false, textContent:'', innerHTML:'', disabled:false, click(){}});
  return elements.get(id);
};
let lastBlob, link;
const context = vm.createContext({
  document: {getElementById:element, createElement:()=>link={click(){}}},
  Blob, URL:{createObjectURL(blob){lastBlob=blob;return 'blob:test'},revokeObjectURL(){}},
  setTimeout(){return 1}, clearTimeout(){}, console, fetch:async(path,options)=>{if(path==='/api/export'){const body=JSON.parse(options.body);lastBlob=new Blob([body.content]);return {ok:true,json:async()=>({url:'/exports/test.csv',filename:'test.csv'})}}return {ok:true,json:async()=>({local_model:true})}},
});
vm.runInContext(fs.readFileSync('app.js','utf8'), context);
vm.runInContext(`
columns=['texte','note','analyse_sentiment']; filename='test.csv';
rows=[
 {index:1,text:'Très mauvais colis',rating:1,sentiment:'Négatif',themes:['Livraison'],evidence:['mauvais'],duplicate:false,method:'test',source:{texte:'=1+1',note:'1',analyse_sentiment:'source conservée'}},
 {index:2,text:'Excellent',rating:5,sentiment:'Positif',themes:[],evidence:['excellent'],duplicate:false,method:'test',source:{texte:'Excellent',note:'5',analyse_sentiment:''}},
 {index:3,text:'',rating:null,sentiment:'Sans texte',themes:[],evidence:[],duplicate:false,method:'test',source:{texte:'',note:'',analyse_sentiment:''}}
];
$('sentiment').value='Négatif';$('theme').value='Livraison';apply();
`, context);
assert.match(element('resultcount').textContent, /^1 sur 3/);
// Régression : la catégorie la plus fréquente ne doit pas remplir l'échelle.
vm.runInContext(`bars('sentiments',[['Positif',98],['Sans texte',287]],500);bars('themes',[['Produit / qualité',84]],500)`,context);
assert.match(element('sentiments').innerHTML,/width:19\.6%/);
assert.match(element('sentiments').innerHTML,/98 · 19,6 %/);
assert.match(element('sentiments').innerHTML,/287 · 57,4 %/);
assert.match(element('themes').innerHTML,/width:16\.8%/);
assert.match(element('themes').innerHTML,/84 · 16,8 %/);
vm.runInContext(`bars('themes',[['Livraison',0]],0)`,context);
assert.match(element('themes').innerHTML,/Aucun avis sélectionné/);
assert.doesNotMatch(element('themes').innerHTML,/NaN|Infinity/);
vm.runInContext(`apply()`,context);
assert.match(element('sentiments').innerHTML,/1 · 100 %/);
element('export').onclick();
(async()=>{
  const csv = await lastBlob.text();
  assert.match(csv, /_analyse_sentiment/);
  assert.match(csv, /"'=1\+1"/);
  assert.match(csv, /source conservée/);
  assert.equal(csv.split('\r\n').length,2);
  element('json').onclick();
  const json=JSON.parse(await lastBlob.text());
  assert.equal(json.length,1);
  assert.equal(json[0].source.texte,'=1+1');
  assert.equal(json[0].analyse.sentiment,'Négatif');
  vm.runInContext(`reset();$('min').value='2';apply()`,context);
  assert.equal(element('mean').textContent,'5');
  assert.match(element('resultcount').textContent,/^1 sur 3/);
  vm.runInContext(`$('search').value='introuvable';apply()`,context);
  assert.match(element('body').innerHTML,/Aucun avis/);
  vm.runInContext(`reset();$('body').onchange({target:{dataset:{index:'1'},value:'Positif'}});$('corrected').checked=true;apply()`,context);
  assert.match(element('resultcount').textContent,/^1 sur 3/);
  element('json').onclick();
  const corrected=JSON.parse(await lastBlob.text());
  assert.equal(corrected[0].analyse.correction_manuelle,true);
  assert.equal(corrected[0].analyse.sentiment_initial,'Négatif');
  assert.equal(corrected[0].analyse.sentiment,'Positif');
  console.log('OK : filtres combinés, notes manquantes, aucun résultat, CSV sécurisé, colonnes préservées, JSON.');
})().catch(error=>{console.error(error);process.exitCode=1});
