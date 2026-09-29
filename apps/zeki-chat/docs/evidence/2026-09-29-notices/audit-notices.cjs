const fs=require('fs'),p=require('path'),crypto=require('crypto');
const report={vendorNoticeFiles:[],vendorLicenseMetadata:[],independentNoticeCount:0,independentNotices:{}};
function scan(d){for(const e of fs.readdirSync(d,{withFileTypes:true})){const f=p.join(d,e.name);if(e.isSymbolicLink())continue;if(e.isDirectory()){scan(f);continue;}if(!e.isFile())continue;
if(/license|notice|copying/i.test(e.name)&&fs.statSync(f).size<2000000){const t=fs.readFileSync(f,'utf8');if(/copyright[^\n]*rocket[.\s-]*chat/i.test(t))report.vendorNoticeFiles.push(f);else if(/copyright/i.test(t)){report.independentNoticeCount++;report.independentNotices[f]=crypto.createHash('sha256').update(t).digest('hex');}}
if(e.name==='package.json'){let v;try{v=JSON.parse(fs.readFileSync(f,'utf8'));}catch{continue;}if(/^@rocket\.chat\//.test(v.name||'')&&!['@rocket.chat/node-poplib','@rocket.chat/poplib'].includes(v.name)&&(Object.hasOwn(v,'license')||Object.hasOwn(v,'licenses')))report.vendorLicenseMetadata.push(f);}
}}
scan('/app/bundle');
const reference='/app/bundle/programs/server/npm/node_modules/whatwg-mimetype/LICENSE.txt';
report.independentReferenceSha256=crypto.createHash('sha256').update(fs.readFileSync(reference)).digest('hex');
console.log(JSON.stringify(report,null,2));
