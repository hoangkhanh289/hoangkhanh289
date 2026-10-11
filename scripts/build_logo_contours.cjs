// Optional authoring step: bake energy walls from the original SVG logo paths.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.platform==='win32'?{channel:'msedge'}:{})});
 try{
  const page=await browser.newPage();
  await page.setContent(fs.readFileSync(path.join(__dirname,'orbit-materials.svg'),'utf8'));
  const data=await page.evaluate(()=>{
   const result={};const ns='http://www.w3.org/2000/svg';
   const distance=(p,a,b)=>{const dx=b.x-a.x,dy=b.y-a.y;let t=((p.x-a.x)*dx+(p.y-a.y)*dy)/(dx*dx+dy*dy);t=Math.max(0,Math.min(1,t));return Math.hypot(p.x-a.x-t*dx,p.y-a.y-t*dy);};
   const simplify=pts=>{
    if(pts.length<=2)return pts;
    let far=0,index=0;for(let i=1;i<pts.length-1;i++){const d=distance(pts[i],pts[0],pts.at(-1));if(d>far){far=d;index=i;}}
    return far>.02?[...simplify(pts.slice(0,index+1)).slice(0,-1),...simplify(pts.slice(index))]:[pts[0],pts.at(-1)];
   };
   for(const [brand,name] of Object.entries({esp:'espressif',st:'stmicroelectronics',nordic:'nordicsemiconductor',pi:'raspberrypi'})){
    const paths=[...document.querySelectorAll(`#logo-${name} path`)].map(n=>n.getAttribute('d'));
    const full=paths.map(d=>new Path2D(d));const ctx=document.createElement('canvas').getContext('2d');
    const filled=(x,y)=>full.some(p=>ctx.isPointInPath(p,x,y));const contours=[];let maxError=0;
    for(const d of paths){
     let previous={x:0,y:0};
     for(const chunk of d.trim().split(/(?=[Mm])/).filter(Boolean)){
      let absolute=chunk;
      if(chunk[0]==='m'){
       const nums=[...chunk.matchAll(/[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?/g)];
       const rest=chunk.slice(nums[1].index+nums[1][0].length).trim();
       absolute=`M${previous.x+Number(nums[0][0])} ${previous.y+Number(nums[1][0])}`+(/^[a-zA-Z]/.test(rest)?rest:'l'+rest);
      }
      const node=document.createElementNS(ns,'path');node.setAttribute('d',absolute);
      previous=node.getPointAtLength(node.getTotalLength());node.setAttribute('d',node.getAttribute('d')+'Z');const length=node.getTotalLength();
      if(length<.01)continue;
      const count=Math.ceil(length/.12),samples=Array.from({length:count+1},(_,i)=>{const p=node.getPointAtLength(length*i/count);return{x:p.x,y:p.y};});
      if(Math.hypot(samples[0].x-samples.at(-1).x,samples[0].y-samples.at(-1).y)>.01)throw Error('Unclosed logo contour');
      let far=1;for(let i=2;i<samples.length-1;i++)if(Math.hypot(samples[i].x-samples[0].x,samples[i].y-samples[0].y)>Math.hypot(samples[far].x-samples[0].x,samples[far].y-samples[0].y))far=i;
      const pts=[...simplify(samples.slice(0,far+1)).slice(0,-1),...simplify(samples.slice(far)).slice(0,-1)];
      for(const p of samples)maxError=Math.max(maxError,Math.min(...pts.map((a,i)=>distance(p,a,pts[(i+1)%pts.length]))));
      const sides=pts.map((a,i)=>{
       const b=pts[(i+1)%pts.length],dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy),mx=(a.x+b.x)/2,my=(a.y+b.y)/2;
       let nx=dy/len,ny=-dx/len;let left=filled(mx+nx*.09,my+ny*.09),right=filled(mx-nx*.09,my-ny*.09);
       if(left===right)return 'skip';
       if(left){nx=-nx;ny=-ny;}
       return nx+ny>0?(nx>ny?'right':'left'):'back';
      });
      contours.push({points:pts.map(p=>[+p.x.toFixed(4),+p.y.toFixed(4)]),sides});
     }
    }
    result[brand]={logo:name,paths,contours,maxChordError:+maxError.toFixed(5)};
   }
   return result;
  });
  for(const value of Object.values(data)){
   value.source_sha256=crypto.createHash('sha256').update(value.paths.join('\n')).digest('hex');delete value.paths;
  }
  fs.writeFileSync(path.join(__dirname,'logo-energy-contours.json'),JSON.stringify({sampling_step:.12,simplification_tolerance:.02,brands:data})+'\n');
  console.log(JSON.stringify(Object.fromEntries(Object.entries(data).map(([k,v])=>[k,{contours:v.contours.length,vertices:v.contours.reduce((s,c)=>s+c.points.length,0),maxChordError:v.maxChordError,skipped:v.contours.reduce((s,c)=>s+c.sides.filter(x=>x==='skip').length,0)}])),null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
