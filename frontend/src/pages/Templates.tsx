import { useEffect, useState } from 'react';
import { fetchTemplates, fetchTemplate, createTemplate, updateTemplate, deleteTemplate, previewTemplate } from '../services/api';

export default function Templates() {
  const [ts, setTs] = useState<any[]>([]);
  const [sel, setSel] = useState('');
  const [tpl, setTpl] = useState<any>(null);
  const [edit, setEdit] = useState(false);
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [vendor, setVendor] = useState('generic');
  const [cmds, setCmds] = useState('');
  const [preview, setPreview] = useState<string[]>([]);
  const [vars, setVars] = useState<Record<string,string>>({});

  const load = () => fetchTemplates().then(setTs);
  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (sel) fetchTemplate(sel).then(t => {
      setTpl(t);
      if (!edit) { setName(t.name); setDesc(t.description||''); setVendor(t.vendor); setCmds((t.config_commands||[]).join('\n')); }
      const v: Record<string,string> = {};
      (t.variables||[]).forEach((x:any) => { v[x.name]=x.default||''; });
      setVars(v);
    });
  }, [sel]);

  const handleSave = async () => {
    const p = { name, description: desc, vendor, config_commands: cmds.split('\n').filter(Boolean) };
    if (!sel || tpl?.source==='builtin') { const r = await createTemplate(p); setSel(r.id); }
    else await updateTemplate(sel, p);
    setEdit(false); load();
  };

  const handlePreview = async () => {
    const r = await previewTemplate({ config_commands: cmds.split('\n').filter(Boolean), variables: vars });
    setPreview(r.commands);
  };

  const handleDelete = async () => { await deleteTemplate(sel); setSel(''); setTpl(null); load(); };

  return (
    <div>
      <h1>Templates</h1>

      <div style={{display:'flex',gap:8}}>
        <div style={{width:280}}>
          <button onClick={() => { setSel(''); setTpl(null); setEdit(true); setName(''); setDesc(''); setCmds(''); setVendor('generic'); }}
            style={{marginBottom:4}}>New Template</button>
          <div style={{maxHeight:500,overflow:'auto'}}>
            {ts.map(t => (
              <div key={t.id} onClick={() => { setSel(t.id); setEdit(false); }}
                style={{padding:'4px 6px',cursor:'pointer',borderBottom:'1px solid #ddd',fontSize:12,
                  background: sel===t.id ? '#b0c8e0' : undefined}}>
                <b>{t.name}</b> <span style={{color:'#666'}}>({t.vendor})</span>
                {t.source==='builtin' && <span style={{color:'#048',fontWeight:'bold'}}> [built-in]</span>}
                {t.is_default && <span style={{color:'#080'}}> [default]</span>}
              </div>
            ))}
          </div>
        </div>

        <div style={{flex:1}}>
          {edit ? (
            <fieldset>
              <legend>{tpl?.id ? 'Edit Template' : 'New Template'}</legend>
              <table style={{border:'none'}}><tbody>
                <tr><td style={{border:'none',padding:2}}><label>Name:</label></td><td style={{border:'none',padding:2}}><input value={name} onChange={e=>setName(e.target.value)} style={{width:300}} /></td></tr>
                <tr><td style={{border:'none',padding:2}}><label>Vendor:</label></td><td style={{border:'none',padding:2}}><select value={vendor} onChange={e=>setVendor(e.target.value)}>
                  {['mikrotik','tplink','ubiquiti','generic','any'].map(v=><option key={v} value={v}>{v}</option>)}
                </select></td></tr>
                <tr><td style={{border:'none',padding:2}}><label>Description:</label></td><td style={{border:'none',padding:2}}><input value={desc} onChange={e=>setDesc(e.target.value)} style={{width:300}} /></td></tr>
              </tbody></table>
              <div style={{marginTop:8}}>
                <label>Commands:</label>
                <textarea value={cmds} onChange={e=>setCmds(e.target.value)} rows={10}
                  style={{width:'100%',fontFamily:'monospace',fontSize:12}}
                  placeholder={"/ip dhcp-server disable [find]\n/user set [find name=admin] password={{{admin_password}}}"} />
              </div>
              <div style={{marginTop:8}}>
                <label>Variables:</label>
                <div style={{display:'flex',gap:4,flexWrap:'wrap',marginTop:4}}>
                  {Object.entries(vars).map(([k,v]) => (
                    <div key={k}><span style={{fontSize:11,color:'#666'}}>{k}</span> <input value={v} onChange={e=>setVars({...vars,[k]:e.target.value})} style={{width:120}} /></div>
                  ))}
                </div>
              </div>
              <div style={{display:'flex',gap:4,marginTop:8}}>
                <button className="btn-primary" onClick={handleSave}>Save</button>
                <button onClick={handlePreview}>Preview</button>
                <button onClick={() => setEdit(false)}>Cancel</button>
                {tpl?.id && tpl.source!=='builtin' && <button className="btn-danger" onClick={handleDelete}>Delete</button>}
              </div>
            </fieldset>
          ) : tpl ? (
            <fieldset>
              <legend>{tpl.name} ({tpl.vendor})</legend>
              <div style={{marginBottom:8,fontSize:12,color:'#666'}}>{tpl.description}</div>
              <pre style={{background:'#fff',border:'1px solid #999',padding:8,fontFamily:'monospace',fontSize:12,maxHeight:300,overflow:'auto'}}>
                {(tpl.config_commands||[]).join('\n')}
              </pre>
              <div style={{marginTop:8,display:'flex',gap:4}}>
                {tpl.source !== 'builtin' && <button onClick={() => setEdit(true)}>Edit</button>}
                <button onClick={handlePreview}>Preview</button>
              </div>
            </fieldset>
          ) : <div style={{color:'#666',padding:20}}>Select a template or create new.</div>}

          {preview.length > 0 && (
            <fieldset style={{marginTop:8}}>
              <legend>Preview</legend>
              <pre style={{background:'#fff',border:'1px solid #999',padding:8,fontSize:12}}>{preview.join('\n')}</pre>
            </fieldset>
          )}
        </div>
      </div>
    </div>
  );
}
