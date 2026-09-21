// Run on nanobase-cm against the deployed portal, no mocked network or data.
const {createRequire}=require('node:module');
const fs=require('node:fs');
const {chromium}=createRequire('/data/nanobaseai/mobile-qa/portal/package.json')('playwright');
(async()=>{
 const dir='/tmp/editor-context-474cb2d9';
 const cookie=fs.readFileSync(dir+'/session.cookie','utf8').trim();
 const split=cookie.indexOf('=');
 const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 const results=[];
 for(const width of [320,390,768,1440]){
  const context=await browser.newContext({viewport:{width,height:1000}});
  await context.addCookies([{name:cookie.slice(0,split),value:cookie.slice(split+1),domain:'portal.nanobase.ai',path:'/timas/',secure:true,httpOnly:true,sameSite:'Strict'}]);
  const page=await context.newPage();
  await page.goto('https://portal.nanobase.ai/timas/editoryal',{waitUntil:'domcontentloaded',timeout:60000});
  const box=page.getByRole('textbox',{name:"ZEKİ AI'ya soru"});
  await box.waitFor({timeout:60000});await box.fill('Takip sorusu yazılabiliyor.');
  await page.screenshot({path:dir+'/portal-'+width+'.png',fullPage:true});
  const dimensions=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth}));
  const rect=await box.boundingBox();
  results.push({width,...dimensions,inputVisible:await box.isVisible(),sendEnabled:await page.getByRole('button',{name:'Gönder',exact:true}).isEnabled(),inputHeight:rect.height,overflow:dimensions.scrollWidth>width});
  await context.close();
 }
 const context=await browser.newContext({viewport:{width:390,height:1000}});
 await context.addCookies([{name:cookie.slice(0,split),value:cookie.slice(split+1),domain:'portal.nanobase.ai',path:'/timas/',secure:true,httpOnly:true,sameSite:'Strict'}]);
 const page=await context.newPage();const sent=[];const replies=[];
 page.on('request',r=>{if(r.method()==='POST' && r.url().endsWith('/api/v1/editorial/ask'))sent.push(r.postDataJSON());});
 page.on('response',async r=>{if(r.url().includes('/api/v1/editorial/ask/') && r.status()===200){try{const d=await r.json();if(d.status==='bitti')replies.push(d);}catch{}}});
 await page.goto('https://portal.nanobase.ai/timas/editoryal',{waitUntil:'domcontentloaded',timeout:60000});
 const input=page.getByRole('textbox',{name:"ZEKİ AI'ya soru"}),send=page.getByRole('button',{name:'Gönder',exact:true});
 await input.fill('Dünyanın En Korkak Hayvanı kitabında Baba Vombat ve Yavru Vombat aynı kişi mi? Kısaca söyle.');
 await send.click();await input.fill('Az önce hangi iki karakteri sordum? Yalnız adlarını yaz.');
 await page.waitForTimeout(1000);const blockedWhileWaiting=await send.isDisabled();
 await page.waitForFunction(()=>{const b=document.querySelector('button[aria-label="Gönder"]');return b&&!b.disabled;},{},{timeout:600000});
 await send.click();await input.fill('Gönderilmeyecek taslak');
 await page.waitForFunction(()=>{const b=document.querySelector('button[aria-label="Gönder"]');return b&&!b.disabled;},{},{timeout:600000});
 const ids=[...new Set(replies.map(r=>r.id))];
 const last=replies.filter(r=>r.id===ids[1]).at(-1);
 const lifecycle={blockedWhileWaiting,sent,answerIds:ids,parentLinked:sent.length===2&&sent[1].parentId===ids[0],followupCorrect:!!last&&['baba','yavru','vombat'].every(x=>last.answer.toLowerCase().includes(x)),answers:ids.map(id=>replies.find(r=>r.id===id))};
 await page.screenshot({path:dir+'/conversation-390.png',fullPage:true});
 fs.writeFileSync(dir+'/lifecycle.json',JSON.stringify(lifecycle,null,2));console.log(JSON.stringify(lifecycle));
 await context.close();
 await browser.close();fs.writeFileSync(dir+'/browser.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exit(1)});
