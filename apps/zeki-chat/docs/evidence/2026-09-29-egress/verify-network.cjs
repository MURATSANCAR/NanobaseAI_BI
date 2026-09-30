const net=require('node:net');
const dns=require('node:dns').promises;
const fs=require('node:fs');
const {spawnSync}=require('node:child_process');
if(!net.isIP(process.env.ZEKI_PROBE_GATEWAY||''))throw new Error('A verified bridge gateway IP is required');
const checks=[];
async function check(name,fn,expected){let success=false,error;try{await Promise.race([fn(),new Promise((_,reject)=>setTimeout(()=>reject(new Error('timeout')),4000))]);success=true;}catch(e){error=e.code||e.message;}checks.push({name,connected:success,error,expected,passed:success===expected});}
function connect(host,port){return new Promise((resolve,reject)=>{const socket=net.connect({host,port});socket.setTimeout(3000);socket.once('connect',()=>{socket.destroy();resolve();});socket.once('error',reject);socket.once('timeout',()=>{socket.destroy();reject(new Error('timeout'));});});}
(async()=>{
await check('real-mongo',()=>connect('zeki-mongo',27017),true);
await check('vendor-dns',()=>dns.lookup('cloud.rocket.chat'),false);
await check('raw-node-vendor-https',()=>fetch('https://rocket.chat/',{signal:AbortSignal.timeout(3000)}),false);
await check('direct-public-ipv4',()=>connect('1.1.1.1',443),false);
await check('direct-public-ipv6',()=>connect('2606:4700:4700::1111',443),false);
await check('host-proxy-detour',()=>connect(process.env.ZEKI_PROBE_GATEWAY,4000),false);
const deno=spawnSync('/bin/deno',['eval',`try{await fetch('https://cloud.rocket.chat/',{signal:AbortSignal.timeout(3000)});console.log('CONNECTED');Deno.exit(1)}catch(e){console.log('BLOCKED:'+e.name)}`],{encoding:'utf8',timeout:5000});
checks.push({name:'deno-direct-fetch',passed:deno.status===0&&deno.stdout.startsWith('BLOCKED:'),result:deno.stdout.trim(),status:deno.status});
console.log(JSON.stringify({checks,allPassed:checks.every(x=>x.passed),routes:fs.readFileSync('/proc/net/route','utf8'),ipv6Routes:fs.readFileSync('/proc/net/ipv6_route','utf8')},null,2));
if(!checks.every(x=>x.passed))process.exitCode=1;
})();
