// Run on the server against the actual application and actual book records.
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const base=(process.env.EDITOR_VERIFY_BASE_URL||'http://127.0.0.1:8810').replace(/\/$/,'');
const {chromium}=require(path.join(root,'runtime/browser-check/node_modules/playwright'));
(async()=>{
 const token=fs.readFileSync(path.join(root,'secrets/api_token'),'utf8').trim();
 const run=JSON.parse(fs.readFileSync(path.join(root,process.env.EDITOR_VERIFY_RUN_FILE||'evidence/reference-book-run.json'),'utf8'));
 const out=path.join(root,'evidence/review-ui');fs.mkdirSync(out,{recursive:true,mode:0o700});
 const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 const results=[];
 try{
  for(const width of [320,390,768,1440]){
   const context=await browser.newContext({viewport:{width,height:1000}});
   const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto(base+'/editor/');
   await page.getByLabel('Operatör erişim anahtarı').waitFor();
   const loginOverflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
   if(loginOverflow)throw new Error('Login horizontal overflow '+width);
   if(width===390)await page.screenshot({path:path.join(out,'login-390.png'),fullPage:true});
   await page.getByLabel('Operatör erişim anahtarı').fill(token);
   await page.getByRole('button',{name:'Çalışma alanını aç'}).click();
   await page.locator('footer code').waitFor({state:'attached',timeout:30000});
   const generation=(await page.locator('footer code').textContent()).trim();
   if(generation!==(run.job||run).generation_id)throw new Error('UI selected another generation');
   await page.locator('.source-image').waitFor({timeout:30000});
   await page.waitForFunction(()=>document.querySelector('.source-image')?.naturalWidth>0);
   if(process.env.EDITOR_VERIFY_RUN_FILE){
    await page.getByRole('heading',{name:'Metin okumaları uyuşuyor',exact:true}).or(page.getByRole('heading',{name:'İnceleme gerekiyor',exact:true})).waitFor({timeout:30000});
    const spansResponse=await context.request.get(base+'/v1/generations/'+generation+'/source_spans?pdf_page=1&limit=100',{headers:{Authorization:'Bearer '+token}});
    const spans=await spansResponse.json();if(!spans.items?.length)throw new Error('Real page spans missing');
    const details=page.locator('.source-notes details').first();await details.locator('summary').click();
    if(!(await details.textContent()).includes(spans.items[0].data.text))throw new Error('UI span differs from API');
    await details.getByRole('button',{name:'Kaynakta göster',exact:true}).click();
    const overlay=await page.locator('.source-highlight').evaluate(element=>{
      const box=element.getBoundingClientRect(),parent=element.parentElement.getBoundingClientRect();
      return [(box.x-parent.x)/parent.width,(box.y-parent.y)/parent.height,box.width/parent.width,box.height/parent.height];
    });
    if(overlay.some((value,i)=>Math.abs(value-spans.items[0].data.bbox[i])>.003))throw new Error('Source highlight differs from API bbox');
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('Expanded source span overflow');
    await page.screenshot({path:path.join(out,'spans-'+width+'.png'),fullPage:true});
   }
   if(process.env.EDITOR_VERIFY_OCR_VL==='1'){
    for(const number of [29,38]){
     const response=await context.request.get(base+'/v1/generations/'+generation+'/source-review?pdf_page='+number,
       {headers:{Authorization:'Bearer '+token}});
     if(!response.ok())throw new Error('OCR review API failed');
     const review=await response.json();
     const regions=review.pages[0].regions.filter(r=>r.ocr_vl);
     const candidate=regions.find(r=>!r.ocr_vl.complete)||regions[0];
     if(!candidate)throw new Error('Real OCR candidate missing');
     await page.locator('#page').selectOption(String(number));
     await page.waitForFunction(n=>document.querySelector('.source-image')?.alt.includes(n+'. sayfası')&&document.querySelector('.source-image')?.naturalWidth>0,number);
     const detail=page.locator('[data-span-id="'+candidate.span_id+'"]');
     await detail.locator('summary').click();
     await detail.locator('.ocr-fallback').waitFor();
     if(!(await detail.locator('.ocr-fallback').textContent()).includes(candidate.ocr_vl.text))throw new Error('OCR UI differs from real API');
     if(!candidate.ocr_vl.complete&&!(await detail.textContent()).includes('Tamamlanmayan çıktı'))throw new Error('Truncated OCR not identified');
     if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('OCR candidate overflow '+width);
     await page.screenshot({path:path.join(out,'ocr-'+number+'-'+width+'.png'),fullPage:true});
    }
   }
   await page.locator('#page').selectOption('6');
   await page.waitForFunction(()=>document.querySelector('.source-image')?.alt.includes('6. sayfası')&&document.querySelector('.source-image')?.naturalWidth>0);
   if(await page.locator('.source-highlight').count())throw new Error('Stale source highlight after page change');
   const checks=[];
   for(const name of ['Kaynak & görsel','Sahneler','Karakter & varlık','Olaylar','Kitap yorumu','Soru & cevap']){
    await page.getByRole('button',{name,exact:true}).click();
    const layout=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,
      smallButtons:[...document.querySelectorAll('button')].filter(x=>x.getBoundingClientRect().height>0&&x.getBoundingClientRect().height<43).length}));
    if(layout.scroll>width||layout.smallButtons)throw new Error('Layout failed '+JSON.stringify({name,layout}));
    checks.push({tab:name,...layout});
   }
   const response=await context.request.get(base+'/v1/generations/'+generation+'/scenes?limit=100',
      {headers:{Authorization:'Bearer '+token}});
   if(!response.ok())throw new Error('Real scene API failed');
   const scenes=(await response.json()).items;
   if(scenes.length){
    await page.getByRole('button',{name:'Sahneler',exact:true}).click();
    await page.locator('.cards .paper').first().waitFor();
    const card=page.locator('.cards .paper').first();
    if(!(await card.textContent()).includes(scenes[0].data.summary))throw new Error('UI scene differs from real API');
    await card.getByText('Sahneden çıkarılan adaylar',{exact:true}).click();
    for(const entity of scenes[0].data.entities){
     if(!(await card.textContent()).includes(entity.description))throw new Error('UI omitted scene entity');
    }
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('Expanded scene overflow '+width);
    await page.screenshot({path:path.join(out,'scenes-'+width+'.png'),fullPage:true});
    const link=card.locator('.refs button').first();
    const expectedPage=(await link.textContent()).match(/\d+/)[0];
    await link.click();
    await page.getByRole('heading',{name:'PDF sayfası '+expectedPage,exact:true}).waitFor();
    await page.waitForFunction(n=>document.querySelector('.source-image')?.alt.includes(n+'. sayfası')&&document.querySelector('.source-image')?.naturalWidth>0,expectedPage);
   }
   await page.getByRole('button',{name:'Kaynak & görsel',exact:true}).click();
   await page.locator('#page').selectOption('6');
   await page.waitForFunction(()=>document.querySelector('.source-image')?.alt.includes('6. sayfası')&&document.querySelector('.source-image')?.naturalWidth>0);
   await page.screenshot({path:path.join(out,'source-'+width+'.png'),fullPage:true});
   if(errors.length)throw new Error('Browser errors '+errors.join('; '));
   if(await page.evaluate(()=>localStorage.length||sessionStorage.length))throw new Error('Unexpected persisted browser state');
   await page.getByRole('button',{name:'Çıkış',exact:true}).click();
   if(await page.getByLabel('Operatör erişim anahtarı').inputValue())throw new Error('Credential remained after logout');
   results.push({width,generation,checks,scene_candidates_compared_to_real_api:scenes.length>0,logout_clears_credential:true});
   await context.close();
  }
  fs.writeFileSync(path.join(out,'verification.json'),JSON.stringify({environment:'remote Chrome / real Editor HTTP API and PostgreSQL',api:base,results,semantic_acceptance:false},null,2));
  console.log(JSON.stringify({viewports:results.map(r=>r.width),tabs:6,source_page:6,horizontal_overflow:false,semantic_acceptance:false}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
