// Server only: compile presentation.ts with the installed esbuild; use the authenticated catalog exported by financial-audit-sql-acceptance.py.
const fs=require('fs');
const {accountingText,checkExplanations}=require('/tmp/audit-presentation.cjs');
const catalog=JSON.parse(fs.readFileSync('/tmp/financial-audit-live-catalog.json','utf8'));
const forbidden=/yazılımc|grid|girid|tekrarlayalım|yazdıralım|yazalım|kullanalım|ekrana/iu;
const failures=[];
for(const item of catalog.items){for(const key of ['title','section','text']){const value=accountingText(item[key]);const at=value.search(forbidden);if(at>=0)failures.push({id:item.id,key,excerpt:value.slice(Math.max(0,at-90),at+150)});}}
for(const page of catalog.pages){const value=accountingText(page.text);const at=value.search(forbidden);if(at>=0)failures.push({page:page.page,excerpt:value.slice(Math.max(0,at-90),at+150)});}
const report={environment:'nanobase-direct; presentation function over actual authenticated API catalog',items:catalog.items.length,pages:catalog.pages.length,explanations:Object.keys(checkExplanations).length,failures,status:failures.length?'FAIL':'PASS'};
fs.writeFileSync('/tmp/financial-audit-language-evidence.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));process.exitCode=failures.length?1:0;
