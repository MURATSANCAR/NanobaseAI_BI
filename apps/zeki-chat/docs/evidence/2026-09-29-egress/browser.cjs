const fs = require('fs');
const { chromium } = require('/home/administrator/zeki-ai-chat/node_modules/playwright');
const dir = '/tmp/codex-zeki-egress';
const auth = JSON.parse(fs.readFileSync(dir + '/session.json', 'utf8'));
const tokens = new Set();
const hosts = new Set();
const results = [];
const forbiddenNetworkRequests=[];
let securityEvidence;
const base = 'https://portal.nanobase.ai';
(async () => {
  const browser = await chromium.launch({executablePath: "/home/administrator/.cache/ms-playwright/chromium-1187/chrome-linux/chrome", headless: true, args: ['--no-sandbox', '--host-resolver-rules=MAP portal.nanobase.ai 127.0.0.1']});
  try {
    for (const width of [320, 390, 768, 1440]) {
      const context = await browser.newContext({viewport:{width,height:900},ignoreHTTPSErrors:true,hasTouch:width<768});
      await context.addCookies([{name:'__Secure-timas_session',value:auth.token,domain:'portal.nanobase.ai',path:'/timas/',httpOnly:true,secure:true,sameSite:'Strict'}]);
      await context.route('**/*', async route => {
        const u=new URL(route.request().url());
        if(['http:','https:'].includes(u.protocol)&&u.hostname!=='portal.nanobase.ai') {forbiddenNetworkRequests.push({host:u.hostname,type:route.request().resourceType()});await route.abort();return;}
        await route.continue();
      });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(e.name));
      page.on('request', r => {try{hosts.add(new URL(r.url()).hostname)}catch{}});
      page.on('response', async r => {
        if(new URL(r.url()).pathname === '/timas/auth/chat-sso' && r.ok()) {
          try {
            const d = await r.json();
            if(d.loginToken) {tokens.add(d.loginToken);fs.writeFileSync(dir+'/chat-tokens.json',JSON.stringify([...tokens]),{mode:0o600});}
          } catch {}
        }
      });
      const navigation=await page.goto(base+'/timas/sohbet/',{waitUntil:'domcontentloaded',timeout:60000});
      let authenticated = false;
      try {
        await page.locator('[aria-label="Kullanıcı menüsü"], [aria-label="User menu"]').first().waitFor({state:'visible',timeout:45000});
        authenticated = true;
      } catch {}
      if(width===320 && authenticated) {
        const csp=navigation.headers()['content-security-policy']||'';
        if(!csp.includes("connect-src 'self'")||csp.includes('connect-src *'))throw new Error('Strict CSP missing; no probes sent');
        const worker=await context.request.get(base+'/timas/sohbet/enc.js');
        securityEvidence={csp,workerStatus:worker.status(),workerContentType:worker.headers()['content-type']||'',workerSourceHasHandler:(await worker.text()).includes('addEventListener'),workerCsp:worker.headers()['content-security-policy']||'',probes:await page.evaluate(async()=>{
          const violations=[];const listener=e=>violations.push({directive:e.effectiveDirective,blockedURI:e.blockedURI});
          document.addEventListener('securitypolicyviolation',listener);
          let fetchBlocked=false,websocketBlocked=false;
          try{await fetch('https://collector.rocket.chat/zeki-egress-probe')}catch{fetchBlocked=true;}
          websocketBlocked=await new Promise(resolve=>{
            try{const ws=new WebSocket('wss://open.rocket.chat/websocket');ws.onerror=()=>resolve(true);ws.onopen=()=>{ws.close();resolve(false)};setTimeout(()=>{ws.close();resolve(false)},1500)}catch{resolve(true)}
          });
          const img=new Image();img.src='https://rocket.chat/zeki-egress-probe.png';document.body.append(img);
          const frame=document.createElement('iframe');frame.src='https://cloud.rocket.chat/zeki-egress-probe';document.body.append(frame);
          try{new Worker('https://rocket.chat/zeki-egress-worker.js')}catch{}
          const anchor=document.createElement('a');anchor.href='https://rocket.chat/';anchor.target='_blank';document.body.append(anchor);
          const click=new MouseEvent('click',{bubbles:true,cancelable:true,composed:true});anchor.dispatchEvent(click);
          await new Promise(r=>setTimeout(r,800));
          img.remove();frame.remove();anchor.remove();document.removeEventListener('securitypolicyviolation',listener);
          return{fetchBlocked,websocketBlocked,vendorLinkBlocked:click.defaultPrevented,violations};
        })};
      }
      await page.waitForTimeout(3000);
      if(width===320 && authenticated) {
        const token=[...tokens].at(-1);
        if(!token)throw new Error('SSO token not captured');
        const subscriptions=await context.request.get(base+'/timas/sohbet/api/v1/subscriptions.get',{headers:{'X-Auth-Token':token,'X-User-Id':auth.userId}});
        const payload=await subscriptions.json();
        if(!subscriptions.ok()||!payload.success||!Array.isArray(payload.update))throw new Error('Real subscriptions API failed');
        fs.writeFileSync(dir+'/subscriptions-api.json',JSON.stringify(payload.update.map(x=>({_id:x._id,rid:x.rid,unread:x.unread||0}))),{mode:0o600});
      }
      const state = await page.evaluate(() => ({title:document.title,width:innerWidth,scrollWidth:document.documentElement.scrollWidth,vendorTextCount:(document.body.innerText.match(/rocket[. ]?chat/gi)||[]).length,overflowing:[...document.querySelectorAll('body *')].map(e=>({tag:e.tagName,classes:e.className,rect:e.getBoundingClientRect()})).filter(x=>x.rect.width && x.rect.right>innerWidth+1 && x.rect.left<innerWidth).slice(0,12).map(x=>({tag:x.tag,classes:String(x.classes),left:x.rect.left,right:x.rect.right}))}));
      await page.screenshot({path:dir+'/chat-'+width+'.png',fullPage:true});
      results.push({width,authenticated,...state,errors});
      await context.close();
    }
    const directives=new Set((securityEvidence?.probes.violations||[]).map(x=>x.directive));
    if(results.some(r=>!r.authenticated||r.width!==r.scrollWidth||r.vendorTextCount||r.errors.length)||forbiddenNetworkRequests.length||!securityEvidence?.probes.fetchBlocked||!securityEvidence?.probes.websocketBlocked||!securityEvidence?.probes.vendorLinkBlocked||!['connect-src','img-src','frame-src'].every(x=>directives.has(x))||securityEvidence.workerStatus!==200||!securityEvidence.workerSourceHasHandler||!/javascript/.test(securityEvidence.workerContentType)||!securityEvidence.workerCsp.includes("connect-src 'self'"))throw new Error('Live egress/browser acceptance failed');
  } finally {
    await browser.close();
    fs.writeFileSync(dir+'/browser-evidence.json',JSON.stringify({results,attemptedRequestHosts:[...hosts].sort(),forbiddenNetworkRequests,securityEvidence},null,2));
    console.log(JSON.stringify({results,attemptedRequestHosts:[...hosts].sort(),forbiddenNetworkRequests,securityEvidence},null,2));
  }
})().catch(e=>{console.error(e.name+': '+e.message);process.exitCode=1;});
