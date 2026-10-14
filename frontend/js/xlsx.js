// Formatted .xlsx export with no external library (from the prototype, spec §13):
// RTL sheet, title band and meta line, styled header, zebra rows, bold totals, frozen header,
// autofilter, fit-to-width printing, numbers as numbers, references as centred text.
import { fmt, today, toast } from './util.js';

const CRC_T = (()=>{ const t=new Uint32Array(256); for (let n=0;n<256;n++){ let c=n; for (let k=0;k<8;k++) c = c&1 ? 0xEDB88320^(c>>>1) : c>>>1; t[n]=c>>>0; } return t; })();
const crc32 = b => { let c=0xFFFFFFFF; for (let i=0;i<b.length;i++) c = CRC_T[(c^b[i])&0xFF]^(c>>>8); return (c^0xFFFFFFFF)>>>0; };
function zipStore(files){
  const enc=new TextEncoder(), parts=[], central=[]; let off=0;
  const u16=v=>[v&255,(v>>>8)&255], u32=v=>[v&255,(v>>>8)&255,(v>>>16)&255,(v>>>24)&255];
  for (const f of files){ const name=enc.encode(f.name), data=typeof f.data==='string'?enc.encode(f.data):f.data, crc=crc32(data);
    const head=[...u32(0x04034b50),...u16(20),...u16(0x0800),...u16(0),...u16(0),...u16(33),...u32(crc),...u32(data.length),...u32(data.length),...u16(name.length),...u16(0)];
    parts.push(new Uint8Array(head), name, data);
    central.push(new Uint8Array([...u32(0x02014b50),...u16(20),...u16(20),...u16(0x0800),...u16(0),...u16(0),...u16(33),...u32(crc),...u32(data.length),...u32(data.length),...u16(name.length),...u16(0),...u16(0),...u16(0),...u16(0),...u32(0),...u32(off)]), name);
    off += head.length + name.length + data.length; }
  const cdSize = central.reduce((s,a)=>s+a.length,0);
  const end=new Uint8Array([...u32(0x06054b50),...u16(0),...u16(0),...u16(files.length),...u16(files.length),...u32(cdSize),...u32(off),...u16(0)]);
  const all=[...parts,...central,end], out=new Uint8Array(all.reduce((s,a)=>s+a.length,0)); let p=0; for (const a of all){ out.set(a,p); p+=a.length; } return out;
}
const xesc = s => String(s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])).replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g,'');
const colL = i => { let s=''; i++; while(i){ const m=(i-1)%26; s=String.fromCharCode(65+m)+s; i=Math.floor((i-1)/26); } return s; };
// style ids (cellXfs order below)
const XS = {def:0, title:1, sub:2, meta:3, head:4, txt:5, int:6, dec:7, date:8, pct:9, ztxt:10, zint:11, zdec:12, zdate:13, zpct:14, ttxt:15, tint:16, tdec:17, tpct:18, note:19, kvl:20, kvv:21, kvs:22, sec:23, band:24, ctr:25, zctr:26};
const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="3"><numFmt numFmtId="164" formatCode="#,##0;[Red]\\(#,##0\\);&quot;-&quot;"/><numFmt numFmtId="165" formatCode="#,##0.00;[Red]\\(#,##0.00\\);&quot;-&quot;"/><numFmt numFmtId="166" formatCode="dd/mm/yyyy"/></numFmts>
<fonts count="9"><font><sz val="10"/><color rgb="FF1F2933"/><name val="Arial"/></font><font><b/><sz val="16"/><color rgb="FFFFFFFF"/><name val="Arial"/></font><font><b/><sz val="12"/><color rgb="FF1F2933"/><name val="Arial"/></font><font><sz val="9"/><color rgb="FF5B6770"/><name val="Arial"/></font><font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Arial"/></font><font><b/><sz val="10"/><color rgb="FF1F2933"/><name val="Arial"/></font><font><i/><sz val="9"/><color rgb="FF5B6770"/><name val="Arial"/></font><font><b/><sz val="12"/><color rgb="FF154C8C"/><name val="Arial"/></font><font><b/><sz val="13"/><color rgb="FF154C8C"/><name val="Arial"/></font></fonts>
<fills count="7"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF154C8C"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF3F6FA"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFDCE6F2"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF7F9FB"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FF0F3A6B"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="4"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FFC9D3DD"/></left><right style="thin"><color rgb="FFC9D3DD"/></right><top style="thin"><color rgb="FFC9D3DD"/></top><bottom style="thin"><color rgb="FFC9D3DD"/></bottom><diagonal/></border><border><left style="thin"><color rgb="FFC9D3DD"/></left><right style="thin"><color rgb="FFC9D3DD"/></right><top style="medium"><color rgb="FF154C8C"/></top><bottom style="double"><color rgb="FF154C8C"/></bottom><diagonal/></border><border><left/><right/><top/><bottom style="medium"><color rgb="FF154C8C"/></bottom><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="27">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="6" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="right" vertical="center" readingOrder="2"/></xf>
<xf numFmtId="0" fontId="7" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="right" vertical="center" readingOrder="2"/></xf>
<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="right" vertical="center" readingOrder="2"/></xf>
<xf numFmtId="0" fontId="4" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1" readingOrder="2"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center" wrapText="1" readingOrder="2"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="165" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="166" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="9" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center" wrapText="1" readingOrder="2"/></xf>
<xf numFmtId="164" fontId="0" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="165" fontId="0" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="166" fontId="0" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="9" fontId="0" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="5" fillId="4" borderId="2" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center" wrapText="1" readingOrder="2"/></xf>
<xf numFmtId="164" fontId="5" fillId="4" borderId="2" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="165" fontId="5" fillId="4" borderId="2" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="9" fontId="5" fillId="4" borderId="2" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="6" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="right" vertical="top" wrapText="1" readingOrder="2"/></xf>
<xf numFmtId="0" fontId="5" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center" wrapText="1" readingOrder="2"/></xf>
<xf numFmtId="164" fontId="8" fillId="5" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="3" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center" wrapText="1" readingOrder="2"/></xf>
<xf numFmtId="0" fontId="7" fillId="0" borderId="3" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center" readingOrder="2"/></xf>
<xf numFmtId="0" fontId="4" fillId="6" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="right" vertical="center" readingOrder="2"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" readingOrder="2"/></xf>
<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" readingOrder="2"/></xf>
</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`;
const xdate = d => { const t = Date.parse(d+'T00:00:00Z'); return Math.round(t/864e5) + 25569; };
// parse a displayed value into a typed cell
function xcell(raw, ctx={}){
  const t = String(raw ?? '').replace(/[ ‎‏]/g,' ').trim();
  if (typeof raw==='number') return {v:raw, k: ctx.dec||!Number.isInteger(raw) ? 'dec':'int'};
  if (!t) return {v:'', k:'txt'};
  if (/^\d{4}-\d{2}-\d{2}$/.test(t)) return {v:xdate(t), k:'date'};
  let m = t.match(/^(-?[\d,]+(?:\.\d+)?)\s*%$/); if (m) return {v:+m[1].replace(/,/g,'')/100, k:'pct'};
  m = t.match(/^\(?(-?[\d,]+(?:\.(\d+))?)\)?$/); if (m && /\d/.test(m[1]) && !/^0\d/.test(m[1]) && m[1].replace(/[-,.]/g,'').length<=15) return {v:+m[1].replace(/,/g,''), k: (m[2]||ctx.dec) ? 'dec':'int'};
  return {v:t, k: ctx.center && t.length<=14 ? 'ctr' : 'txt'};
}
// blocks: {type:'kv', items:[[label,value,sub]]} | {type:'section', text} | {type:'table', head:[], rows:[[]], foot:[[]], zebra} | {type:'note', text}
export function layoutSheet(name, title, meta, blocks){
  const tables = blocks.filter(b=>b.type==='table');
  const ncol = Math.max(4, ...tables.map(t=>Math.max(t.head.length, ...t.rows.map(r=>r.length), ...(t.foot||[]).map(r=>r.length))));
  const rows=[], merges=[]; let r=0, freeze=null, printRow=null, filter=null;
  const full = (v, s, ht) => { rows.push({ht, cells:[{v, s}]}); merges.push(`A${r+1}:${colL(ncol-1)}${r+1}`); r++; };
  full(FACTORY, XS.title, 30);
  full(title, XS.band, 22);
  full(meta, XS.meta, 18);
  rows.push({cells:[]}); r++;
  const widths = Array(ncol).fill(10);
  const fit = (c, v, k) => { const s = k==='date'?'00/00/0000':k==='int'||k==='dec'? fmt(v, k==='dec'?2:0) : k==='pct'? '100%' : String(v); const w = Math.min(48, Math.ceil(s.length*(/[؀-ۿ]/.test(s)?1.05:1.0))+3); if (w>widths[c]) widths[c]=w; };
  for (const b of blocks){
    if (b.type==='section'){ rows.push({cells:[]}); r++; rows.push({ht:22, cells:Array.from({length:ncol},(_,i)=>({v:i?'':b.text, s:XS.sec}))}); merges.push(`A${r+1}:${colL(ncol-1)}${r+1}`); r++; }
    else if (b.type==='note'){ rows.push({ht: Math.min(90, 15*Math.ceil(b.text.length/(ncol*14))+6), cells:[{v:b.text, s:XS.note}]}); merges.push(`A${r+1}:${colL(ncol-1)}${r+1}`); r++; }
    else if (b.type==='kv'){ for (const [l,v,sub] of b.items){ const c=xcell(v); rows.push({ht:20, cells:[{v:l,s:XS.kvl},{v:c.v, s: (c.k==='int'||c.k==='dec')?XS.kvv:XS.kvl},{v:sub||'',s:XS.kvs}, ...Array.from({length:Math.max(0,ncol-3)},()=>({v:'',s:XS.kvs}))]}); if (ncol>3) merges.push(`C${r+1}:${colL(ncol-1)}${r+1}`); fit(0,l,'txt'); if (c.k==='int'||c.k==='dec') fit(1, Math.abs(c.v)*10, 'int'); r++; } rows.push({cells:[]}); r++; }
    else if (b.type==='table'){
      const decCols = b.head.map(hd=>/ر\.س|سعودي|متوسط|تكلفة الوحدة|للكرتون/.test(hd)), idCols = b.head.map(hd=>/^(القيد|رقم القيد|الفاتورة|المرجع|الرمز|رقم)/.test(hd));
      const tw = Math.max(b.head.length, ...b.rows.map(x=>x.length), ...(b.foot||[]).map(x=>x.length), ...(b.pre||[]).map(x=>x.length));
      rows.push({ht: 32, cells: Array.from({length:tw},(_,i)=>({v:b.head[i]??'', s:XS.head}))});
      if (tables.length===1 && freeze==null){ freeze=r+1; printRow=r+1; filter=`A${r+1}:${colL(Math.max(0,b.head.length-1))}${r+1+b.rows.length}`; }
      b.head.forEach((hd,i)=>{ const w=Math.min(18, hd.length+4); if (w>widths[i]) widths[i]=w; }); r++;
      for (const row of (b.pre||[])){ rows.push({ht:22, cells: Array.from({length:tw},(_,i)=>{ const c=xcell(idCols[i]?String(row[i]??''):row[i], {dec:decCols[i], center:true}); fit(i,c.v,c.k); return {v:c.v, s: c.k==='int'?XS.tint:c.k==='dec'?XS.tdec:c.k==='pct'?XS.tpct:c.k==='date'?XS.date:XS.ttxt}; })}); r++; }
      b.rows.forEach((row,ri)=>{ const z = ri%2===1; rows.push({cells: Array.from({length:tw},(_,i)=>{ const raw=row[i]; const c = idCols[i] && raw!=null && raw!=='' ? {v:String(raw).replace(/,/g,''), k:'ctr'} : xcell(raw, {dec:decCols[i], center: i===0 && b.centerFirst}); fit(i,c.v,c.k); const s = z ? {txt:XS.ztxt,int:XS.zint,dec:XS.zdec,date:XS.zdate,pct:XS.zpct,ctr:XS.zctr}[c.k] : {txt:XS.txt,int:XS.int,dec:XS.dec,date:XS.date,pct:XS.pct,ctr:XS.ctr}[c.k]; return {v:c.v, s}; })}); r++; });
      if (!b.rows.length && b.empty){ rows.push({ht:20, cells:Array.from({length:tw},(_,i)=>({v:i?'':b.empty, s:XS.ztxt}))}); merges.push(`A${r+1}:${colL(Math.max(0,b.head.length-1))}${r+1}`); r++; }
      for (const row of (b.foot||[])){ rows.push({ht:22, cells: Array.from({length:tw},(_,i)=>{ const c=xcell(row[i], {dec:decCols[i]}); fit(i,c.v,c.k); return {v:c.v, s: c.k==='int'?XS.tint:c.k==='dec'?XS.tdec:c.k==='pct'?XS.tpct:c.k==='date'?XS.date:XS.ttxt}; })}); r++; }
      rows.push({cells:[]}); r++;
    }
  }
  return {name, rows, merges, widths, freeze, printRow, filter, ncol};
}
export function buildXlsx(sheets){
  const files=[]; const sh = sheets.map((s,i)=>({...s, name:(s.name||('Sheet'+(i+1))).replace(/[\[\]:*?\/\\]/g,' ').slice(0,31)}));
  files.push({name:'[Content_Types].xml', data:`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>${sh.map((_,i)=>`<Override PartName="/xl/worksheets/sheet${i+1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join('')}</Types>`});
  files.push({name:'_rels/.rels', data:`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>`});
  files.push({name:'docProps/core.xml', data:`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>${xesc(sh[0].name)}</dc:title><dc:creator>${xesc(FACTORY)}</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">${new Date().toISOString().slice(0,19)}Z</dcterms:created></cp:coreProperties>`});
  const defs = sh.map((s,i)=>s.printRow?`<definedName name="_xlnm.Print_Titles" localSheetId="${i}">'${xesc(s.name).replace(/'/g,"''")}'!$${s.printRow}:$${s.printRow}</definedName>`:'').join('') + sh.map((s,i)=>s.filter?`<definedName name="_xlnm._FilterDatabase" localSheetId="${i}" hidden="1">'${xesc(s.name).replace(/'/g,"''")}'!$${s.filter.replace(/([A-Z]+)(\d+):([A-Z]+)(\d+)/,'$1$$$2:$$$3$$$4')}</definedName>`:'').join('');
  files.push({name:'xl/workbook.xml', data:`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView/></bookViews><sheets>${sh.map((s,i)=>`<sheet name="${xesc(s.name)}" sheetId="${i+1}" r:id="rId${i+1}"/>`).join('')}</sheets>${defs?`<definedNames>${defs}</definedNames>`:''}</workbook>`});
  files.push({name:'xl/_rels/workbook.xml.rels', data:`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${sh.map((_,i)=>`<Relationship Id="rId${i+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i+1}.xml"/>`).join('')}<Relationship Id="rId${sh.length+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`});
  files.push({name:'xl/styles.xml', data:STYLES});
  sh.forEach((s,i)=>{
    const rowsXml = s.rows.map((row,ri)=>`<row r="${ri+1}"${row.ht?` ht="${row.ht}" customHeight="1"`:''}>${row.cells.map((c,ci)=>{ const ref=colL(ci)+(ri+1); const st=c.s??0;
      if (c.v==='' || c.v==null) return `<c r="${ref}" s="${st}"/>`;
      if (typeof c.v==='number' && isFinite(c.v)) return `<c r="${ref}" s="${st}"><v>${c.v}</v></c>`;
      return `<c r="${ref}" t="inlineStr" s="${st}"><is><t xml:space="preserve">${xesc(c.v)}</t></is></c>`; }).join('')}</row>`).join('');
    const pane = s.freeze ? `<pane ySplit="${s.freeze}" topLeftCell="A${s.freeze+1}" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft" activeCell="A${s.freeze+1}" sqref="A${s.freeze+1}"/>` : '';
    files.push({name:`xl/worksheets/sheet${i+1}.xml`, data:`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheetPr><pageSetUpPr fitToPage="1"/></sheetPr><sheetViews><sheetView rightToLeft="1" showGridLines="0" workbookViewId="0">${pane}</sheetView></sheetViews><sheetFormatPr defaultRowHeight="18" customHeight="1"/><cols>${s.widths.map((w,c)=>`<col min="${c+1}" max="${c+1}" width="${w}" customWidth="1"/>`).join('')}</cols><sheetData>${rowsXml}</sheetData>${s.filter?`<autoFilter ref="${s.filter}"/>`:''}${s.merges.length?`<mergeCells count="${s.merges.length}">${s.merges.map(m=>`<mergeCell ref="${m}"/>`).join('')}</mergeCells>`:''}<printOptions horizontalCentered="1"/><pageMargins left="0.4" right="0.4" top="0.5" bottom="0.6" header="0.3" footer="0.3"/><pageSetup paperSize="9" orientation="${s.ncol>6?'landscape':'portrait'}" fitToWidth="1" fitToHeight="0"/><headerFooter><oddFooter>&amp;R${xesc(FACTORY)}&amp;Cصفحة &amp;P من &amp;N&amp;L${xesc(today())}</oddFooter></headerFooter></worksheet>`}); });
  return zipStore(files);
}
// read a rendered panel into blocks, in document order
export function panelBlocks(el){
  const blocks=[]; const seen=new Set();
  const cellText = td => { const sel=td.querySelector('select'); if (sel) return sel.selectedOptions[0]?.textContent||''; const inp=td.querySelector('input'); if (inp) return inp.type==='checkbox' ? (inp.checked?'✓':'') : (inp.value || ''); return (td.innerText||td.textContent||'').replace(/\s*\n\s*/g,' · ').trim(); };
  el.querySelectorAll('h3, .kpis, table, p.note, .alert').forEach(n=>{
    if ([...seen].some(s=>s.contains(n))) return; seen.add(n);
    if (n.matches('h3')) blocks.push({type:'section', text:n.textContent.trim()});
    else if (n.matches('.kpis')) blocks.push({type:'kv', items:[...n.querySelectorAll('.kpi')].map(k=>[k.querySelector('.l')?.textContent.trim()||'', (k.querySelector('.v')?.textContent||'').trim(), k.querySelector('.s')?.textContent.trim()||''])});
    else if (n.matches('table')){ const head=[...n.querySelectorAll('thead th')].map(th=>th.textContent.trim()); const body=[], foot=[], pre=[]; let empty='';
      n.querySelectorAll('tbody tr').forEach(tr=>{ const cells=[...tr.children].map(cellText); if (tr.classList.contains('tot')) (body.length||!head.length ? foot : pre).push(cells); else if (cells.length===1 && tr.children[0].colSpan>1) empty=cells[0]; else body.push(cells); });
      n.querySelectorAll('tfoot tr').forEach(tr=>foot.push([...tr.children].map(cellText)));
      if (!head.length && body.length){ const w=Math.max(...body.map(r=>r.length)); head.push(...Array.from({length:w},(_,i)=>i?'القيمة':'البند')); }
      if (head.length) blocks.push({type:'table', head, rows:body, foot, pre, empty}); }
    else if (n.matches('p.note, .alert')){ const t=n.textContent.trim(); if (t) blocks.push({type:'note', text:t}); }
  });
  return blocks;
}
const FACTORY = 'مصنع جوان لصناعة وتجارة البلاستيك';

// Build the workbook in the browser and hand it to the user as a normal download.
export function saveXlsx(filename, sheets) {
  try {
    const bytes = buildXlsx(sheets);
    const url = URL.createObjectURL(new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    toast('جُهّز الملف');
  } catch (e) {
    toast('تعذّر التنزيل: ' + (e?.message || e));
  }
}
