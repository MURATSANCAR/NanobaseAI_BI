// Run on the server against the actual application and actual book records.
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const base=(process.env.EDITOR_VERIFY_BASE_URL||'http://127.0.0.1:8810').replace(/\/$/,'');
const {chromium}=require(path.join(root,'runtime/browser-check/node_modules/playwright'));
(async()=>{
 const token=fs.readFileSync(path.join(root,process.env.EDITOR_VERIFY_TOKEN_FILE||'secrets/api_token'),'utf8').trim();
 if(process.env.EDITOR_VERIFY_TOKEN_FILE){
  const response=await fetch(base+'/v1/me',{headers:{Authorization:'Bearer '+token}});
  const identity=await response.json();
  if(!response.ok||identity.role!=='READER')throw new Error('Expected an actual read-only credential');
 }
 const run=JSON.parse(fs.readFileSync(path.join(root,process.env.EDITOR_VERIFY_RUN_FILE||'evidence/reference-book-run.json'),'utf8'));
 const verifyCharacters=process.env.EDITOR_VERIFY_CHARACTER_EVIDENCE==='1';
 const verifyRegional=process.env.EDITOR_VERIFY_REGIONAL_SOURCE==='1';
 const targetGeneration=(run.job||run).generation_id;
 let regionalSpan=null,targetWork=null,targetJob=null;
 if(verifyRegional){
  const read=async endpoint=>{const response=await fetch(base+'/v1'+endpoint,{headers:{Authorization:'Bearer '+token}});if(!response.ok)throw new Error('Real regional API failed '+response.status);return response.json();};
  targetWork=(await read('/generations/'+targetGeneration)).work_id;
  for(let offset=0;;){
   const batch=await read('/works/'+targetWork+'/analyses?offset='+offset+'&limit=100');
   targetJob=batch.items.find(r=>r.generation_id===targetGeneration)?.id;
   if(targetJob||!batch.has_more)break;if(!batch.items.length)throw new Error('Empty analysis pagination');offset+=batch.items.length;
  }
  if(!targetJob)throw new Error('Target generation analysis unavailable');
  for(let offset=0;;){
   const batch=await read('/generations/'+targetGeneration+'/source_spans?offset='+offset+'&limit=100');
   regionalSpan=batch.items.find(r=>r.data.selected_reader==='REGIONAL_OCR');
   if(regionalSpan||!batch.has_more)break;if(!batch.items.length)throw new Error('Empty regional pagination');offset+=batch.items.length;
  }
  if(!regionalSpan)throw new Error('No actual regional selection available');
 }
 let characterPage=null;
 if(verifyCharacters){
  const generation=(run.job||run).generation_id;const records=[];
  for(let offset=0;;){
   const response=await fetch(base+'/v1/generations/'+generation+'/character_evidence?offset='+offset+'&limit=100',{headers:{Authorization:'Bearer '+token}});
   if(!response.ok)throw new Error('Character evidence API failed '+response.status);
   const batch=await response.json();records.push(...batch.items);
   if(!batch.has_more)break;
   if(!batch.items.length)throw new Error('Empty character evidence pagination');
   offset+=batch.items.length;
  }
  characterPage=records.find(r=>r.data.attributions?.length&&r.data.named_mentions?.length)?.data;
  if(!characterPage)throw new Error('No actual source attribution available for UI acceptance');
 }
 const out=path.join(root,'evidence/review-ui');fs.mkdirSync(out,{recursive:true,mode:0o700});
 const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 const results=[];
 try{
  for(const width of [320,390,768,1440]){
   const context=await browser.newContext({viewport:{width,height:1000}});
   const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto(base+'/editor/');
   await page.getByLabel('Erişim anahtarı').waitFor();
   const loginOverflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
   if(loginOverflow)throw new Error('Login horizontal overflow '+width);
   if(width===390)await page.screenshot({path:path.join(out,'login-390.png'),fullPage:true});
   await page.getByLabel('Erişim anahtarı').fill(token);
   await page.getByRole('button',{name:'Çalışma alanını aç'}).click();
   if(verifyRegional){
    await page.locator('.selectors select').nth(0).selectOption(targetWork);
    await page.locator('.selectors select').nth(1).selectOption(targetJob);
    await page.waitForFunction(expected=>document.querySelector('footer code')?.textContent.trim()===expected,targetGeneration);
   }
   await page.locator('footer code').waitFor({state:'attached',timeout:30000});
   const generation=(await page.locator('footer code').textContent()).trim();
   if(generation!==(run.job||run).generation_id)throw new Error('UI selected another generation');
   await page.locator('.source-image').waitFor({timeout:30000});
   await page.waitForFunction(()=>document.querySelector('.source-image')?.naturalWidth>0);
   if(process.env.EDITOR_VERIFY_RUN_FILE){
    let availableSpan=null;
    for(let offset=0;;){
     const response=await context.request.get(base+'/v1/generations/'+generation+'/source_spans?offset='+offset+'&limit=100',{headers:{Authorization:'Bearer '+token}});
     if(!response.ok())throw new Error('Actual source spans API failed');
     const batch=await response.json();
     availableSpan=batch.items[0]??null;
     if(availableSpan||!batch.has_more)break;
     if(!batch.items.length)throw new Error('Empty source pagination');
     offset+=batch.items.length;
    }
    if(!availableSpan)throw new Error('No actual text span available: positive text/source UI scenario cannot be verified');
    const sourcePage=availableSpan.data.pdf_page;
    await page.locator('#page').selectOption(String(sourcePage));
    await page.waitForFunction(n=>document.querySelector('.source-image')?.alt.includes(n+'. sayfası')&&document.querySelector('.source-image')?.naturalWidth>0,sourcePage);
    await page.getByRole('heading',{name:'Metin okumaları uyuşuyor',exact:true}).or(page.getByRole('heading',{name:'İnceleme gerekiyor',exact:true})).waitFor({timeout:30000});
    const spansResponse=await context.request.get(base+'/v1/generations/'+generation+'/source_spans?pdf_page='+sourcePage+'&limit=100',{headers:{Authorization:'Bearer '+token}});
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
   let regionalCheck=null;
   if(verifyRegional){
    const number=regionalSpan.data.pdf_page;
    await page.getByRole('button',{name:'Kaynak & görsel',exact:true}).click();
    await page.locator('#page').selectOption(String(number));
    await page.waitForFunction(n=>document.querySelector('.source-image')?.alt.includes(n+'. sayfası')&&document.querySelector('.source-image')?.naturalWidth>0,number);
    const detail=page.locator('[data-span-id="'+regionalSpan.id+'"]');
    await detail.waitFor();if(await detail.getAttribute('open')===null)await detail.locator('summary').click();
    const info=detail.getByTestId('regional-source-selection');await info.waitFor();
    const expectedSummary=(regionalSpan.data.status==='TEXT_AGREED'?'✓':'⚠')+' '+regionalSpan.data.text;
    if(await detail.locator('summary').textContent()!==expectedSummary)throw new Error('Selected regional text differs from real API');
    if(await info.locator('p').nth(1).textContent()!=='İlk tam sayfa okuması: '+regionalSpan.data.raw_text)throw new Error('Original full-page text differs from real API');
    if(await info.locator('p').first().textContent()!=='Kaynak metin, diğer okumalarla uyuşan bölgesel okumadan alındı.')throw new Error('Regional selection notice missing');
    if(!(await info.textContent()).includes('bu uyuşma olay veya karakter doğrulaması değildir.'))throw new Error('Regional selection acceptance limit missing');
    await detail.getByRole('button',{name:'Kaynakta göster',exact:true}).click();
    await page.locator('.source-highlight').waitFor();
    const overlay=await page.locator('.source-highlight').evaluate(element=>{const box=element.getBoundingClientRect(),parent=element.parentElement.getBoundingClientRect();return [(box.x-parent.x)/parent.width,(box.y-parent.y)/parent.height,box.width/parent.width,box.height/parent.height];});
    if(overlay.some((v,i)=>Math.abs(v-regionalSpan.data.bbox[i])>.003))throw new Error('Regional source bbox differs from API');
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('Regional source overflow '+width);
    await page.screenshot({path:path.join(out,'regional-source-'+width+'.png'),fullPage:true});
    regionalCheck={span_id:regionalSpan.id,pdf_page:number,raw_and_selected_text_exact:true,selection_notice:true,bbox_equal:true};
   }
   let characterCheck=null;
   if(verifyCharacters){
    const number=characterPage.pdf_page;
    await page.getByRole('button',{name:'Kaynak & görsel',exact:true}).click();
    await page.locator('#page').selectOption(String(number));
    await page.waitForFunction(n=>document.querySelector('.source-image')?.alt.includes(n+'. sayfası')&&document.querySelector('.source-image')?.naturalWidth>0,number);
    const panel=page.getByTestId('text-attributions');await panel.waitFor();
    const items=panel.locator('.claim');
    if(await items.count()!==characterPage.attributions.length)throw new Error('Attribution UI count differs from API');
    for(let index=0;index<characterPage.attributions.length;index++){
     const expected=characterPage.attributions[index],item=items.nth(index);
     if(await item.locator('b').textContent()!==expected.label||await item.locator('blockquote').textContent()!==expected.quote)throw new Error('Literal attribution UI differs from API');
    }
    const expected=characterPage.attributions[0],spanRows=[];
    for(let offset=0;;){
     const response=await context.request.get(base+'/v1/generations/'+generation+'/source_spans?pdf_page='+number+'&offset='+offset+'&limit=100',{headers:{Authorization:'Bearer '+token}});
     if(!response.ok())throw new Error('Character source spans API failed');
     const batch=await response.json();spanRows.push(...batch.items);
     if(!batch.has_more)break;
     if(!batch.items.length)throw new Error('Empty source span pagination');
     offset+=batch.items.length;
    }
    const firstSpan=spanRows.find(r=>r.id===expected.source_span_refs[0]);
    if(!firstSpan||firstSpan.data.pdf_page!==number)throw new Error('Character first source reference missing');
    await items.first().getByRole('button',{name:'Kaynakta göster',exact:true}).click();
    await page.locator('.source-highlight').waitFor();
    const overlay=await page.locator('.source-highlight').evaluate(element=>{
     const box=element.getBoundingClientRect(),parent=element.parentElement.getBoundingClientRect();
     return [(box.x-parent.x)/parent.width,(box.y-parent.y)/parent.height,box.width/parent.width,box.height/parent.height];
    });
    if(overlay.some((value,i)=>Math.abs(value-firstSpan.data.bbox[i])>.003))throw new Error('Character highlight differs from first source ref bbox');
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('Character attribution overflow '+width);
    await page.screenshot({path:path.join(out,'text-attributions-'+width+'.png'),fullPage:true});
    await page.getByRole('button',{name:'Karakter & varlık',exact:true}).click();
    const card=page.getByTestId('named-mention').filter({has:page.getByRole('heading',{name:expected.label,exact:true})});
    if(await card.count()!==1)throw new Error('Named mention card missing or ambiguous');
    if(await card.locator('h2').textContent()!==expected.label)throw new Error('Named mention label differs from API');
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('Named mention overflow '+width);
    await page.screenshot({path:path.join(out,'named-mention-'+width+'.png'),fullPage:true});
    await card.getByRole('button',{name:'Kaynak: sayfa '+number,exact:true}).click();
    await page.getByRole('heading',{name:'PDF sayfası '+number,exact:true}).waitFor();
    await page.getByTestId('text-attributions').waitFor();
    if(await page.locator('#page').inputValue()!==String(number))throw new Error('Named mention returned to wrong page');
    characterCheck={pdf_page:number,attributions:characterPage.attributions.length,literal_api_equal:true,first_ref_bbox_equal:true,named_mention_source_navigation:true};
   }
   const currentSourcePage=verifyCharacters?characterPage.pdf_page:verifyRegional?regionalSpan.data.pdf_page:null;
   const resetPage=(verifyCharacters||verifyRegional)?await page.locator('#page option').evaluateAll((options,current)=>options.find(option=>option.value!==String(current))?.value||String(current),currentSourcePage):'6';
   await page.locator('#page').selectOption(resetPage);
   await page.waitForFunction(n=>document.querySelector('.source-image')?.alt.includes(n+'. sayfası')&&document.querySelector('.source-image')?.naturalWidth>0,resetPage);
   if((currentSourcePage===null||resetPage!==String(currentSourcePage))&&await page.locator('.source-highlight').count())throw new Error('Stale source highlight after page change');
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
   await page.locator('#page').selectOption(resetPage);
   await page.waitForFunction(n=>document.querySelector('.source-image')?.alt.includes(n+'. sayfası')&&document.querySelector('.source-image')?.naturalWidth>0,resetPage);
   await page.screenshot({path:path.join(out,'source-'+width+'.png'),fullPage:true});
   if(errors.length)throw new Error('Browser errors '+errors.join('; '));
   if(await page.evaluate(()=>localStorage.length||sessionStorage.length))throw new Error('Unexpected persisted browser state');
   await page.getByRole('button',{name:'Çıkış',exact:true}).click();
   if(await page.getByLabel('Erişim anahtarı').inputValue())throw new Error('Credential remained after logout');
   results.push({width,generation,checks,character_evidence:characterCheck,regional_source:regionalCheck,scene_candidates_compared_to_real_api:scenes.length>0,logout_clears_credential:true});
   await context.close();
  }
  fs.writeFileSync(path.join(out,'verification.json'),JSON.stringify({environment:'remote Chrome / real Editor HTTP API and PostgreSQL',api:base,results,semantic_acceptance:false},null,2));
  console.log(JSON.stringify({viewports:results.map(r=>r.width),tabs:6,character_evidence:verifyCharacters,character_source_page:characterPage?.pdf_page??null,horizontal_overflow:false,semantic_acceptance:false}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
