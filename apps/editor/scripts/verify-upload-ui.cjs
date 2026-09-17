// Run only on a real connected installation with the original user-provided PDF.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'runtime/browser-check/node_modules/playwright'));
const base=process.env.EDITOR_VERIFY_BASE_URL;
const source=process.env.EDITOR_VERIFY_PDF;
if(!base||!source)throw new Error('Explicit real API and original PDF are required');
(async()=>{
 const token=fs.readFileSync(path.join(root,'secrets/api_token'),'utf8').trim();
 const bytes=fs.readFileSync(source),hash=crypto.createHash('sha256').update(bytes).digest('hex');
 const out=path.join(root,'evidence/upload-ui');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 const result={api:base,source_sha256:hash,source_bytes:bytes.length,viewports:[],semantic_acceptance:false};
 const reuse=process.env.EDITOR_VERIFY_REUSE_UPLOAD==='1';
 try{
  for(const width of [320,390,768,1440]){
   const context=await browser.newContext({viewport:{width,height:1000}});const page=await context.newPage();
   await page.goto(base+'/editor/');
   await page.getByLabel('Erişim anahtarı').fill(token);
   await page.getByRole('button',{name:'Çalışma alanını aç'}).click();
   await page.locator('.upload-book summary').click();
   await page.getByLabel('Kitap adı',{exact:true}).fill('Ekrana Sığmayan Macera — gerçek yükleme kabulü');
   await page.getByLabel('Baskı / sürüm',{exact:true}).fill('Özgün PDF, değişiklik yapılmadı');
   await page.getByLabel('PDF dosyası',{exact:true}).setInputFiles(source);
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('Upload layout overflow '+width);
   await page.screenshot({path:path.join(out,'form-'+width+'.png'),fullPage:true});
   result.viewports.push(width);
   if(width===390){
    let body;
    if(reuse){
      body={id:JSON.parse(fs.readFileSync(path.join(out,'verification.json'),'utf8')).upload_id};
      await page.getByLabel('Önceki yüklemeyi takip et').selectOption(body.id);
    }else{
    const completed=page.waitForResponse(r=>r.url().endsWith('/complete')&&r.request().method()==='POST',{timeout:120000});
    await page.getByRole('button',{name:'Yükle ve kaynağı hazırla',exact:true}).click();
    const response=await completed;body=await response.json();
    if(response.status()!==202||body.status!=='PARSING')throw new Error('Cold source did not enter parser queue '+JSON.stringify(body));
    }
    result.upload_id=body.id;
    // Reload demonstrates that tracking is recovered from durable API state.
    await page.reload();
    await page.getByLabel('Erişim anahtarı').fill(token);
    await page.getByRole('button',{name:'Çalışma alanını aç'}).click();
    await page.locator('.upload-book summary').click();
    await page.getByLabel('Önceki yüklemeyi takip et').selectOption(body.id);
    fs.writeFileSync(path.join(out,'running.json'),JSON.stringify(result,null,2));
    console.log(JSON.stringify({stage:reuse?'TRACKING_RESTORED':'PARSING',upload_id:body.id,reload_tracking:true}));
    await page.getByRole('button',{name:'Kitap analizini başlat',exact:true}).waitFor({timeout:3700000});
    const headers={Authorization:'Bearer '+token};
    const status=await (await context.request.get(base+'/v1/uploads/'+body.id,{headers})).json();
    if(status.status!=='COMPLETED'||!status.content_version_id)throw new Error('Upload did not complete');
    const manifest=await (await context.request.get(base+'/v1/source-probes/'+hash,{headers})).json();
    if(manifest.sha256!==hash||manifest.bytes!==bytes.length||!manifest.source_accounting_complete)throw new Error('Actual API source differs from uploaded original');
    result.status=status;result.pages=manifest.pdf_pages;result.reload_tracking=true;
    await page.screenshot({path:path.join(out,'ready-390.png'),fullPage:true});
    console.log(JSON.stringify({stage:'SOURCE_READY',pages:manifest.pdf_pages,upload_id:body.id}));
   }
   await page.getByRole('button',{name:'Çıkış',exact:true}).click();
   if(await page.getByLabel('Erişim anahtarı').inputValue())throw new Error('Credential persisted after logout');
   await context.close();
  }
  fs.writeFileSync(path.join(out,reuse?'verification-final.json':'verification.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
