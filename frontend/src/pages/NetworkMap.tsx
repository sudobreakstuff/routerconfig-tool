import { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import { fetchDevices } from '../services/api';

export default function NetworkMap() {
  const svgRef = useRef<SVGSVGElement>(null);
  const [devices, setDevices] = useState<any[]>([]);

  useEffect(() => { fetchDevices().then(setDevices).catch(()=>{}); }, []);

  useEffect(() => {
    const svg = d3.select(svgRef.current);
    const el = svgRef.current?.parentElement;
    if (!el) return;
    const w = el.clientWidth, h = el.clientHeight;
    svg.selectAll('*').remove();
    svg.attr('width', w).attr('height', h);

    const nodes: any[] = [{ id:'internet', label:'Internet', type:'wan', online:true }];
    const links: any[] = [];
    const cpeSeen = new Set<string>();

    devices.forEach(d => {
      nodes.push({ id:d.id, label:d.name, type:'router', online:d.is_online });
      if (d.ip_address) {
        const cpeIp = d.ip_address.split('.').slice(0,3).join('.')+'.1';
        if (!cpeSeen.has(cpeIp)) {
          cpeSeen.add(cpeIp);
          nodes.push({ id:'cpe-'+cpeIp, label:'CPE .1', type:'cpe', online:true });
          links.push({ source:'internet', target:'cpe-'+cpeIp, type:'wan' });
        }
        links.push({ source:'cpe-'+cpeIp, target:d.id, type:'lan' });
      }
    });

    if (nodes.length <= 1) return;

    const g = svg.append('g');
    svg.call(d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.3, 3]).on('zoom', (e) => g.attr('transform', e.transform)) as any);

    const sim = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id((d:any)=>d.id).distance(130))
      .force('charge', d3.forceManyBody().strength(-500))
      .force('center', d3.forceCenter(w/2,h/2))
      .force('collision', d3.forceCollide(55));

    g.append('g').selectAll('line').data(links).join('line')
      .attr('stroke','#999').attr('stroke-width',1.5).attr('stroke-dasharray',(d:any)=>d.type==='wan'?'4 3':'');

    const ng = g.append('g').selectAll('g').data(nodes).join('g')
      .call(d3.drag<any,any>().on('start',(e,d)=>{if(!e.active)sim.alphaTarget(0.3).restart();d.fx=d.x;d.fy=d.y;})
        .on('drag',(e,d)=>{d.fx=e.x;d.fy=e.y;}).on('end',(e,d)=>{if(!e.active)sim.alphaTarget(0);d.fx=null;d.fy=null;}));

    ng.append('circle').attr('r',(d:any)=>d.type==='cpe'?20:d.type==='router'?24:14)
      .attr('fill',(d:any)=>!d.online?'#999':d.type==='cpe'?'#336':d.type==='router'?'#080':'#048')
      .attr('stroke','#fff').attr('stroke-width',2);

    ng.append('text').text((d:any)=>d.label.length>16?d.label.slice(0,15):d.label)
      .attr('text-anchor','middle').attr('dy',(d:any)=>d.type==='cpe'?-30:-34)
      .attr('fill','#000').attr('font-size',11).attr('font-weight','bold');

    ng.append('text').text((d:any)=>d.type.toUpperCase())
      .attr('text-anchor','middle').attr('dy',(d:any)=>d.type==='cpe'?32:36)
      .attr('fill','#666').attr('font-size',9);

    sim.on('tick',()=>{
      g.selectAll<SVGLineElement,any>('line').attr('x1',d=>d.source.x).attr('y1',d=>d.source.y).attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);
      ng.attr('transform',d=>`translate(${d.x},${d.y})`);
    });
    sim.on('end',()=>sim.stop());
    const safety = setTimeout(()=>sim.stop(), 15000);

    return () => {
      clearTimeout(safety);
      sim.stop();
      svg.selectAll('*').remove();
    };
  }, [devices]);

  return (
    <div style={{display:'flex',flexDirection:'column',height:'calc(100vh - 150px)'}}>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:8}}>
        <h1 style={{margin:0}}>Network Map</h1>
        <div style={{display:'flex',gap:8,alignItems:'center',fontSize:11}}>
          <span style={{color:'#336'}}>CPE</span>
          <span style={{color:'#080'}}>Router</span>
          <span style={{color:'#999'}}>Offline</span>
          <button onClick={async () => setDevices(await fetchDevices())} className="btn-sm">Refresh</button>
        </div>
      </div>
      <div className="card" style={{flex:1,overflow:'hidden'}}>
        {devices.length===0 && <div style={{position:'absolute',inset:0,display:'flex',alignItems:'center',justifyContent:'center',color:'#666'}}>No devices to display</div>}
        <svg ref={svgRef} style={{width:'100%',height:'100%'}} />
      </div>
    </div>
  );
}
