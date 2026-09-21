// Server only: exercise the shipped renderer against freshly read real API rows.
const fs=require('fs');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const {rowExplanation,accountExplanation,balanceSignExplanation,findingSummary}=require('/tmp/audit-findings.cjs');
const FindingReason=require('/tmp/audit-finding-reason.cjs').default;
const live=JSON.parse(fs.readFileSync('/tmp/audit-findings-live.json','utf8'));
const failures=[];let rendered=0;
const fmt=new Intl.NumberFormat('tr-TR',{minimumFractionDigits:2,maximumFractionDigits:4});
function verify(id,explanation,tokens){
  const html=renderToStaticMarkup(React.createElement(FindingReason,{explanation}));rendered++;
  for(const token of ['Sorun ne?','Neden işaretlendi?','Ne kontrol edilmeli?',...tokens])if(!html.includes(String(token)))failures.push({id,missing:token});
  if((/tanımlı değil|undefined|yazılımc/iu.test(html)||html.includes('NaN')))failures.push({id,reason:'unsupported or invalid explanation'});
}
for(const [key,rows] of Object.entries(live.samples))for(const r of rows){
  const ex=rowExplanation(key,r),tokens=[r.documentNo??r.slipNo??r.slipRef];
  if(key.endsWith('unposted'))tokens.push('işareti: 0',r.sourceRef);
  if(key==='invoice-account')tokens.push(r.sourceRef,'boş veya 0');
  if(key.endsWith('amount')||key==='invoice-vat-ledger'){
    tokens.push(fmt.format(Number(r.expected))+' TL');
    if(r.actual===null){tokens.push('bulunamadı','gerçek bir sıfır');if(ex.evidence.includes('net tutarı: 0,00 TL'))failures.push({key,reason:'missing coerced to zero'});}
    else tokens.push(fmt.format(Number(r.actual))+' TL',fmt.format(Number(r.difference))+' TL','0,01 TL');
  }
  verify(key,ex,tokens);
}
for(const a of live.accounts){
  verify(a.code,balanceSignExplanation(a),[a.code,fmt.format(Number(a.debit))+' TL',fmt.format(Number(a.credit))+' TL',fmt.format(Number(a.balance))+' TL',Number(a.balance)<0?'yerine alacak':'yerine borç']);
  if(a.unexpectedSign)verify(a.code+'-core',accountExplanation(a),[a.code,fmt.format(Number(a.balance))+' TL','tüm hareketlerinin hatalı olduğu anlamına gelmez']);
}
for(const c of [...live.coreChecks,...live.deepChecks].filter(c=>c.status==='finding'))verify(c.id+'-summary',findingSummary(c),[]);
console.log(JSON.stringify({runId:live.runId,rendered,failures,status:failures.length?'FAIL':'PASS'}));process.exitCode=failures.length?1:0;
