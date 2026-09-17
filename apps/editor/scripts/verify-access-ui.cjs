// Real remote Chrome and actual scoped credentials; no fixtures or simulated API.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const root=path.resolve(__dirname,'..'),base=process.env.EDITOR_VERIFY_BASE_URL;
if(!base)throw new Error('Explicit real API required');
const {chromium}=require(path.join(root,'runtime/browser-check/node_modules/playwright'));
(async()=>{
 const operator=fs.readFileSync(path.join(root,'secrets/api_token'),'utf8').trim();
 const keyFile=path.join(root,'secrets/access-verification-reader');
 const reader=fs.readFileSync(keyFile,'utf8').trim();
 const run=JSON.parse(fs.readFileSync(path.join(root,'evidence/access-verification.json'),'utf8'));
 const out=path.join(root,'evidence/access-ui');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 const results=[];
 try{
  for(const width of [320,390,768,1440]){
   for(const role of ['ADMIN','READER']){
    const context=await browser.newContext({viewport:{width,height:1000}});const page=await context.newPage();const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base+'/editor/');await page.getByLabel('Erişim anahtarı',{exact:true}).fill(role==='ADMIN'?operator:reader);
    await page.getByRole('button',{name:'Çalışma alanını aç'}).click();
    await page.getByRole('button',{name:'Çıkış',exact:true}).waitFor();
    if(role==='ADMIN'){
     await page.locator('.access-panel summary').click();
     await page.getByLabel('Erişim verilecek kullanıcı').waitFor();
     await page.waitForFunction(()=>document.querySelector('.access-panel select')?.options.length>0);
     if(!(await page.getByLabel('Erişim verilecek kullanıcı').textContent()).includes('Kurulum yöneticisi'))throw new Error('Actual operator not shown');
     if(!await page.getByText('Yeni kitap yükle',{exact:true}).count())throw new Error('Administrator lost upload UI');
    }else{
     if(await page.locator('.access-panel').count()||await page.getByText('Yeni kitap yükle',{exact:true}).count())throw new Error('Reader sees write controls');
    }
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);if(overflow)throw new Error('Access UI overflow '+role+' '+width);
    if(errors.length)throw new Error(errors.join(';'));
    await page.screenshot({path:path.join(out,role.toLowerCase()+'-'+width+'.png'),fullPage:true});
    if(await page.evaluate(()=>localStorage.length||sessionStorage.length))throw new Error('Unexpected persistent browser state');
    await page.getByRole('button',{name:'Çıkış',exact:true}).click();
    if(await page.getByLabel('Erişim anahtarı',{exact:true}).inputValue())throw new Error('Credential remains after logout');
    results.push({width,role,horizontal_overflow:false,role_controls_correct:true});await context.close();
   }
  }
  fs.writeFileSync(path.join(out,'verification.json'),JSON.stringify({api:base,results,real_user_accounts:1},null,2));console.log(JSON.stringify({results}));
 }finally{
  await browser.close();
  // Revoke the temporary browser credential through the actual administrator API.
  const response=await fetch(base+'/v1/access/keys/'+run.credential_ids[0]+'/revoke',{method:'POST',headers:{Authorization:'Bearer '+operator,'Content-Type':'application/json','Idempotency-Key':'access-ui-revoke:'+crypto.randomUUID()},body:JSON.stringify({reason:'Gerçek tarayıcı kabul kontrolü tamamlandı'})});
  if(!response.ok)throw new Error('Reader verification credential could not be revoked');
  const denied=await fetch(base+'/v1/me',{headers:{Authorization:'Bearer '+reader}});if(denied.status!==401)throw new Error('Revoked reader credential still works');
  fs.unlinkSync(keyFile);
 }
})().catch(e=>{console.error(e.message);process.exitCode=1;});
