import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const config = JSON.parse(await readFile(process.argv[2], 'utf8'));
const axe = await readFile(require.resolve('axe-core/axe.min.js'), 'utf8');
const servers = [];
async function serve(root) {
  const server = createServer(async (req, res) => {
    const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    let path = resolve(root, '.' + pathname);
    if (path !== root && !path.startsWith(root + sep)) { res.writeHead(403).end(); return; }
    if (!pathname.split('/').at(-1).includes('.')) path = resolve(path, 'index.html');
    try { const data = await readFile(path); res.setHeader('Content-Type', path.endsWith('.html') ? 'text/html' : path.endsWith('.css') ? 'text/css' : path.endsWith('.js') ? 'text/javascript' : 'application/octet-stream'); res.end(data); }
    catch { res.writeHead(404).end('Not found'); }
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r)); servers.push(server);
  return `http://127.0.0.1:${server.address().port}`;
}
let browser;
try {
  browser = await chromium.launch({headless:true, ...(process.env.SITEGRAPH_CHROMIUM_EXECUTABLE ? {executablePath:process.env.SITEGRAPH_CHROMIUM_EXECUTABLE, args:['--no-sandbox','--disable-dev-shm-usage','--no-zygote']} : {})});
  const origins = {baseline:await serve(config.baseline), candidate:await serve(config.candidate)};
  const evidence = [], pages = [];
  for (const [label, origin] of Object.entries(origins)) {
    for (const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
      const context = await browser.newContext({viewport, reducedMotion:'reduce'});
      // Only the isolated local artifact may be loaded. No external requests.
      await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
      const page = await context.newPage();
      for (const route of config.routes) {
        const url = origin + route;
        const response = await page.goto(url, {waitUntil:'networkidle'});
        await page.addScriptTag({content:axe});
        const accessibility = await page.evaluate(async () => {
          const result = await window.axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});
          return {violations:result.violations.map(v=>({id:v.id, impact:v.impact, description:v.description, nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),
                  incomplete:result.incomplete.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)})), passes:result.passes.length};
        });
        const dom = await page.evaluate(() => ({title:document.title,description:document.querySelector('meta[name="description"]')?.content || '',canonical:document.querySelector('link[rel="canonical"]')?.href || '',robots:document.querySelector('meta[name="robots"]')?.content || '',h1:document.querySelectorAll('h1').length,
          links:[...document.querySelectorAll('a[href]')].map(a=>a.getAttribute('href')).filter(h=>h.startsWith('/')&&!h.startsWith('//')),
          facts:[...document.querySelectorAll('[data-fact]')].map(n=>({id:n.getAttribute('data-fact'),value:n.textContent.trim(),visible:!!(n.getClientRects().length)&&getComputedStyle(n).visibility!=='hidden'}))}));
        let keyboard = null;
        if (route === '/pricing') {
          const cta = page.locator('section[aria-labelledby="starter-heading"] a.button');
          let reached = false;
          // Reload clears focus before checking the actual tab sequence.
          await page.reload({waitUntil:'networkidle'});
          for (let i=0; i<60; i++) {await page.keyboard.press('Tab'); if (await cta.evaluate(n=>n===document.activeElement).catch(()=>false)) {reached=true;break;}}
          keyboard={selector:'section[aria-labelledby="starter-heading"] a.button',reachable:reached};
        }
        const destinations=[];
        for (const href of [...new Set(dom.links)]) {
          const target=new URL(href,origin); const r=await context.request.get(target.href);
          destinations.push({href,status:r.status()});
        }
        pages.push({artifact:label,route,url,viewport,status:response.status(),seo:dom,accessibility,keyboard,destinations});
      }
      await context.close();
    }
  }
  if(!config.facts)evidence.push({domain:'facts',code:'authority_unavailable',route:'*',detail:'No supplied fact authority; factual consistency was not assessed.'});
  for (const candidate of pages.filter(p=>p.artifact==='candidate')) {
    const baseline=pages.find(p=>p.artifact==='baseline'&&p.route===candidate.route&&p.viewport.width===candidate.viewport.width);
    const add=(domain,code,detail)=>evidence.push({domain,code,route:candidate.route,viewport:candidate.viewport,detail});
    if(candidate.status!==200)add('seo','route_response',`Candidate returned ${candidate.status}`);
    for(const key of ['title','description','canonical']) {
      if(!candidate.seo[key])add('seo','missing_'+key,`Rendered ${key} is empty`);
      else if(candidate.seo[key]!==baseline.seo[key])add('seo',key+'_changed',{before:baseline.seo[key],after:candidate.seo[key]});
    }
    if(/noindex/i.test(candidate.seo.robots))add('seo','noindex','Rendered robots includes noindex');
    if(candidate.seo.h1!==1)add('seo','heading_structure',`Expected one h1; observed ${candidate.seo.h1}`);
    for(const d of candidate.destinations)if(d.status>=400)add('seo','broken_internal_link',d);
    for(const violation of candidate.accessibility.violations)add('accessibility',violation.id,{...violation,baseline_present:baseline.accessibility.violations.some(v=>v.id===violation.id)});
    if(candidate.keyboard&&!candidate.keyboard.reachable)add('accessibility','cta_keyboard_unreachable',candidate.keyboard);
    if(config.facts) {
      for(const fact of candidate.seo.facts) {
        const expected=config.facts.facts[fact.id];
        if(expected===undefined||fact.value!==expected||!fact.visible)add('facts','policy_mismatch',{...fact,expected:expected??null,authority:config.facts.authority});
      }
      for(const [id,routes]of Object.entries(config.facts.required_routes||{}))if(routes.includes(candidate.route)&&!candidate.seo.facts.some(f=>f.id===id&&f.visible))add('facts','required_fact_missing',{id,authority:config.facts.authority});
    }
  }
  console.log(JSON.stringify({status:evidence.length?'review_required':'completed',domain_results:Object.fromEntries(['seo','accessibility','facts'].map(domain=>[domain,{status:evidence.some(e=>e.domain===domain)?'review_required':'completed'}])),tool:{browser:browser.version(),playwright:require('playwright/package.json').version,axe:require('axe-core/package.json').version},conditions:{viewports:[1440,390],reduced_motion:'reduce',network:'isolated local artifacts only'},evidence,pages,
    limitations:['Selected axe rules and one CTA tab sequence do not establish full accessibility compliance.','SEO checks establish rendered metadata and local destinations, not indexing or ranking.','Facts cover only marked occurrences and required routes against supplied fixture authority; unmarked claims and external truth are not assessed.','Metadata changes require review; this runner does not infer authorization from prose.']}));
} finally { if(browser)await browser.close(); for(const s of servers)await new Promise(r=>s.close(r)); }
