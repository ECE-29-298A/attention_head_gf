from pathlib import Path
import re,json,hashlib,zipfile,html
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
pdfmetrics.registerFont(TTFont('Helvetica','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
pdfmetrics.registerFont(TTFont('Helvetica-Bold','/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
pdfmetrics.registerFontFamily('Helvetica',normal='Helvetica',bold='Helvetica-Bold',italic='Helvetica',boldItalic='Helvetica-Bold')

R=Path(__file__).resolve().parent;P=R/'attention-extended/physical';O=R/'output/pdf';O.mkdir(parents=True,exist_ok=True)
summary=json.loads((P/'run6/summary.json').read_text());ppa={}
for short,corner in [('tt','tt_025C_1v80'),('ss','ss_100C_1v60'),('ff','ff_n40C_1v95')]:
 log=(P/f'report_ppa_{short}.log').read_text();tim=(P/f'report_ppa/timing_{corner}.rpt').read_text()
 slacks=[float(x) for x in re.findall(r'([\d.-]+)\s+slack \(MET\)',tim)]
 powers=[]
 for match in re.finditer(r'^Total\s+([\deE+.-]+)\s+([\deE+.-]+)\s+([\deE+.-]+)\s+([\deE+.-]+)',log,re.M):powers.append(list(map(float,match.groups())))
 if short=='ss' and len(powers)==3:
  m=re.search(r'^Total\s+([\deE+.-]+)\s+([\deE+.-]+)\s+([\deE+.-]+)\s+([\deE+.-]+)',(P/'report_ss_power.log').read_text(),re.M);powers.append(list(map(float,m.groups())))
 assert len(powers)==4
 ppa[short]=dict(corner=corner,hold_ns=slacks[0],setup_ns=slacks[1],min_period_ns=100-slacks[1],conditional_fmax_MHz=1000/(100-slacks[1]),power_W=dict(zip(['0','0.05','0.1','0.2'],powers)))
(P/'report_ppa/results.json').write_text(json.dumps(ppa,indent=2))
sections=[]
def section(title,subtitle=''):
 s={'title':title,'subtitle':subtitle,'items':[]};sections.append(s);return s['items']
def para(s,t):s.append(('p',t))
def table(s,rows,widths=None):s.append(('table',rows,widths))
def heading(s,t):s.append(('h',t))

s=section('Single-tile attention accelerator','ECE 298A | Engineering report | 25 September 2026')
para(s,'A host-streamed INT8 attention engine with reusable linear and normalization operations, implemented in one SKY130 high-density standard-cell tile. This report consolidates routed-layout measurements, fresh static-timing and vectorless-power analysis, functional verification, and pretrained SmolLM2 integration results.')
table(s,[['Metric','Result','Evidence class'],['Tile footprint','161 x 111.52 um; 0.017955 mm2','Routed geometry'],['Non-filler cell area','13,865.80 um2','Placed cells'],['Tile / placement-core occupancy','77.226% / 84.069%','Geometric utilization'],['Registers / total instances','148 / 2,597 including fillers','Netlist / layout'],['Reference operating clock','10 MHz','Prior timing-checked target'],['Conditional worst-corner fmax',f"{ppa['ss']['conditional_fmax_MHz']:.2f} MHz",'Static timing; not silicon'],['Typical power, 10 MHz, activity 0.1',f"{ppa['tt']['power_W']['0.1'][3]*1e3:.4f} mW",'Vectorless estimate'],['Safe full-range attention shape','128 keys x 64 dimensions','Bounded RTL verification']], [0.37,0.35,0.28])
heading(s,'Verdict')
para(s,'The fixed candidate fits the one-tile geometry and passes the available physical checks. Full attention runs through RTL during pretrained SmolLM2 generation. One complete pretrained decoder block is also executable, but quantizing all 30 blocks with the tested scheme produces garbled output. Functional agreement with an integer reference is not proof of model-quality preservation.')
para(s,'This is a custom feasibility implementation, not a completed shuttle sign-off or a fabricated chip measurement. There is no on-chip tensor SRAM. The model weights, tensors, and execution scheduling are external. Power and maximum frequency remain conditional estimates, not lab measurements.')

s=section('Architecture and numerical contract','One datapath, many sequential operations')
para(s,'The complete attention operation is O = softmax(Q K^T / sqrt(d_k)) V. All three arithmetic stages execute in the core. Heads and layers are time-multiplexed rather than replicated in silicon.')
table(s,[['Stage / extension','What the circuit does'],['Scores','Serial INT8 multiply-accumulate; maximum-score tracking. Scores are recomputed for the exponential pass.'],['Approximate softmax','Power-of-two scaling; small exponential lookup; denominator accumulation. The host caches emitted weights and replays them unchanged.'],['Weighted output','Unsigned weight x signed V accumulation; integer normalization division.'],['Linear operations','Expose MAC and saturating, shifted INT8 output for projections, residuals, gating and RoPE multiply-adds.'],['RMS normalization','Sum of squares; integer square root via successive odd-number subtraction; normalization; learned gamma in a following multiply.'],['Activations','Two-entry attention approximates SiLU and other nonlinearities using the existing datapath.']], [0.28,0.72])
para(s,'Fixed implementation: norm_odd.v, NB=7, DB=6, SERIAL=1. Shared accumulator and weighted accumulator: 23 bits; maximum-score register: 22 bits; denominator: 15 bits; returned arithmetic codes: 8 bits. The serial multiplier takes eight internal multiply steps plus command and operand-transfer cycles.')
heading(s,'Interface and host responsibilities')
para(s,'The byte input carries commands/operands; send and cmd select transactions. ready, valid and kind identify acceptance and output type. Commands 0-8 cover reset-of-operation, scale load, signed MAC, max update, exponent output, weighted MAC, normalized output, requantized output and square root. The host schedules loops and eligible causal tokens, stores tensors, supplies quantization scales and RoPE constants, and acknowledges returned bytes.')
para(s,'In the full-block LLM experiment, token embeddings and the final vocabulary projection still execute on the CPU. Quantization, scale bookkeeping, cache storage, coefficient generation and sign/operand packing also remain host work. This is a hybrid system, not a stand-alone LLM chip.')
para(s,'RMS uses floor(sqrt(sum(x^2))) with a minimum denominator of one; floating-point epsilon is not reproduced. Attention exponentials and normalization are approximations. Long full-range vectors can overflow: the advertised attention bound does not guarantee arbitrary 576- or 1,536-wide INT8 operations are safe.')

s=section('Area and utilization','Physical occupancy, not the earlier 60% synthesis screen')
rows=[['Cell category','Count','Area (um2)','Tile (%)']]
for x in summary['cell_categories']:rows.append([x['category'],str(x['count']),f"{x['area_um2']:,.2f}",f"{x['percent_tile']:.3f}"])
table(s,rows,[0.44,0.12,0.24,0.20])
para(s,'Non-filler area is 13,865.7984 um2: 77.226% of the entire 17,954.72 um2 tile, but 84.069% of the 16,493.3184 um2 placement core. Fillers occupy 2,627.52 um2, or 15.931% of core sites. All legal row sites are occupied after filler insertion: 100% filler-inclusive core occupancy is expected and is not 100% functional-logic utilization.')
para(s,'There are 13,182 placement sites (338 columns x 39 rows), with 11,082 occupied by non-filler cells. The core rectangle is (2.76, 2.72) to (158.24, 108.80) um. The 2,100 filler sites cannot be treated as guaranteed routable extra logic capacity.')
para(s,'Synthesis plus tie mapping occupied 8,932.3168 um2. Physical implementation added a net 4,933.4816 um2 of non-filler area. Clock distribution is only 2.272% of the tile; hold repair is 16.780%. The old claim that 40% had to be reserved for clocks was not an appropriate interpretation.')
s.append(('image',str(R/'Attention-tile-layout.png')))
para(s,'Actual saved placement and metal geometry. Power and signal routing occupy metal above the cells; their projected areas must not be added to cell area as if they were disjoint floorplan regions. Routing is limited through metal 4 in this candidate.')

s=section('Timing and maximum frequency','Reloaded routed database plus nominal extracted SPEF')
rows=[['Cell corner','Setup slack at 10 MHz','Hold slack','Conditional fmax']]
labels={'tt':'TT / 1.80 V / 25 C','ss':'SS / 1.60 V / 100 C','ff':'FF / 1.95 V / -40 C'}
for c in ['tt','ss','ff']:
 x=ppa[c];rows.append([labels[c],f"+{x['setup_ns']:.4f} ns",f"+{x['hold_ns']:.4f} ns",f"{x['conditional_fmax_MHz']:.2f} MHz"])
table(s,rows,[0.31,0.25,0.19,0.25])
para(s,'For these single-cycle paths and fixed I/O delays, the zero-setup-slack period is T_min = 100 ns - setup slack. f_max = 1000 / T_min in MHz. A clock-period sweep rechecked the netlist, including port paths, around the limiting boundary; this is not just an extrapolation from the nominal clock.')
table(s,[['Slow-corner period / frequency','Setup result'],['25 ns / 40 MHz','+2.8085 ns; passes setup'],['22.2 ns / 45.045 MHz','+0.0085 ns; near-zero margin'],['22.19 ns / 45.065 MHz','Approximately -0.0015 ns; fails setup'],['20 ns / 50 MHz','-2.1915 ns; fails setup']], [0.53,0.47])
heading(s,'Constraints and interpretation')
para(s,'Constraints: maximum I/O delay 10 ns, minimum I/O delay 0 ns, input transition 1 ns, output load 0.01 pF, clock uncertainty 0.5 ns, propagated clock tree. The same nominal interconnect SPEF is used at all three Liberty corners; independent RC-min/RC-max corners, OCV and crosstalk sign-off were not performed. Thirteen constant tie-output endpoints were previously reported unconstrained.')
para(s,'The slow-corner limiting setup path is register-to-register (_2140_ to _2075_). Worst fast-corner hold margin is only 0.0418 ns. The 45.06 MHz value is therefore a conditional STA limit, not a recommended operating point or a board clock guarantee. 10 MHz remains the prior reference target; 40 MHz is a positive-margin STA exploration, not hardware validation.')
para(s,'The fresh TT SPEF-reload run gives +85.1837 ns setup and +0.3346 ns hold. The earlier in-memory extraction report gave +85.9340 ns and about +0.09 ns. This report uses the fresh, consistent SPEF-reload analysis for its timing table and fmax; SS and FF reproduce the archived values. The TT discrepancy remains a flow-consistency item to reconcile before sign-off; neither run changes the worst-corner limit.')
para(s,'Maximum transition and capacitance violation reports are empty at 10 MHz for all three reloaded corners. The frequency sweep checks setup/hold; it is not a complete higher-frequency sign-off covering pulse width, power integrity or the shuttle clock/interface.')

s=section('Power estimate and assumptions','Vectorless, standard-cell-block estimate; not measured consumption')
para(s,'Power was recomputed on the routed database with the nominal SPEF and Liberty internal-power and leakage models at 10 MHz. Non-clock pins are assigned uniform activity alpha and high-state probability 0.5; alpha means transitions per clock period. Clock activity remains enabled. These are sensitivity scenarios, not activity measured from the LLM waveform.')
rows=[['Activity alpha','TT (mW)','SS (mW)','FF (mW)']]
for a in ['0','0.05','0.1','0.2']:rows.append([a]+[f"{ppa[c]['power_W'][a][3]*1e3:.6f}" for c in ['tt','ss','ff']])
table(s,rows,[0.28,0.24,0.24,0.24])
heading(s,'Typical-corner breakdown at alpha = 0.1')
w=ppa['tt']['power_W']['0.1']
table(s,[['Component','Power'],['Internal cell power',f'{w[0]*1e6:.3f} uW'],['Net switching power',f'{w[1]*1e6:.3f} uW'],['Library-model leakage',f'{w[2]*1e9:.3f} nW'],['Total',f'{w[3]*1e6:.3f} uW = {w[3]*1e3:.4f} mW']], [0.55,0.45])
para(s,'At this scenario, the reported sequential, combinational and clock groups are approximately 69.15, 38.91 and 50.59 uW. Clock-group power excludes clock-related internal power counted within sequential cells. Alpha = 0 still consumes about 109.10 uW at TT because the clock continues toggling; it is not powered-off or clock-gated standby.')
para(s,'The SS leakage estimate is approximately 7.31 uW, much higher than the TT estimate of 5.56 nW. These are strongly corner-dependent Liberty-model values, not measurements. Across the sampled scenarios the block total ranges from about 0.092 to 0.242 mW; this range is not a guaranteed min/max consumption envelope.')
heading(s,'What is excluded')
para(s,'The full Tiny Tapeout harness, package and I/O pad drivers, external memories, host computer, bridge interface and board regulators are not modeled. No IR-drop, electromigration, thermal or measured workload/VCD-based power analysis was completed. Uniform activity does not model state-dependent idle behavior or data correlations and is not a glitch-resolved gate-delay simulation.')
para(s,'The original SS multi-scenario log ended before its alpha=0.2 table. That point was rerun in isolation and completed successfully; its separate log is included. No missing point was interpolated. Tool command semantics are documented at https://opensta.readthedocs.io/en/latest/Commands/ (set_power_activity).')

s=section('Functional and pretrained-model verification','Arithmetic correctness and model quality are separate results')
table(s,[['Test','Observed result'],['Physical / gate-level toy block','16 stages, 2,580 outputs, 240,087 cycles; exact integer-reference match.'],['Verilator vs Icarus bridge check','Same outputs and 63,302 cycles; includes 576/1,536-wide dot products, RMS, real attention and SiLU.'],['All SmolLM2 attention heads','24 generated tokens / 3 prompts; 518,400 checked outputs and 45,630 weights; exact integer-reference match.'],['One complete pretrained block','24 generated tokens / 3 prompts; 391,680 checked arithmetic outputs; coherent but changed continuations.'],['All 30 pretrained blocks','4 generated tokens / 1 prompt in RTL; 1,571,328 checked arithmetic outputs; garbled text despite exact reference agreement.']], [0.35,0.65])
para(s,'All RTL paths also match the separate integer model in all 49,152 final logits at every tested generation step. RTL-returned values feed subsequent operations; software reference arithmetic is an assertion oracle, not a substitute in the hardware data path. SmolLM2-135M-Instruct has 30 layers, hidden width 576, intermediate width 1,536, 9 query heads, 3 KV heads and head dimension 64.')
para(s,'Example: all-attention offload continued "The capital of France is" with "Paris. Paris is the political, cultural...". The all-block experiment continued "Hello" with "inying whoinis". The full-block quantization is a quality failure; no faithful full-model deployment is claimed. The three short prompts and overlapping calibration topics are not a held-out model benchmark.')
heading(s,'Range and precision failures')
table(s,[['Directed full-range input','Desired output','RTL output'],['1,536 products of 127 x 127; output shift 17','127','-3'],['576 inputs of 127; RMS numerator factor 384','16','51']], [0.65,0.18,0.17])
para(s,'These intentional range tests expose accumulator wraparound. The actual all-block trace stayed within the checked completed-sum range: maximum absolute linear sum 204,916 and maximum RMS square sum 2,301,595, below the signed 23-bit limit of 4,194,303. Safe arbitrary-input deployment needs range constraints or tiled/multi-pass arithmetic. The poor full-model text is reproduced without those checked range violations.')
para(s,'A separate earlier toy logistic-classifier RTL demonstration performed prediction and learning updates with host-resident weights. It is not LLM training. Likewise, synthetic decoder-block success does not establish pretrained-model accuracy. Complete formal equivalence and exhaustive end-to-end verification have not been performed.')

s=section('Throughput and system implications','Cycle-derived core time, excluding host communication and CPU work')
table(s,[['RTL offload path','Cycles','Core time at 10 MHz','Generated-token rate'],['All attention','103,235,324','10.324 s','2.325 tokens/s'],['First complete block','1,183,981,432','118.398 s','0.203 tokens/s'],['All 30 complete blocks','4,729,280,732','472.928 s','0.00846 tokens/s']], [0.27,0.23,0.25,0.25])
para(s,'The first two measurements each produced 24 generated tokens across three prompts, with 30 processed input positions including prefill. The all-block sample produced four tokens from four processed positions. Rates above use generated tokens divided by all measured core time; they include the respective prompt-processing workload. They are not simulator wall-clock speed or end-to-end system TPS.')
para(s,'All-attention contexts ranged from 1 to 12 tokens. Its 2.325 tokens/s average is not a 128-token-context figure. Attention latency grows with context; prefill repeats attention for every query position. The full-block short-context trace averaged 118.232 s per generated token, or roughly two minutes before communications and remaining host computation.')
para(s,'One processed position through the first-block test averaged about 3.947 s of core time; this differs from 4.933 s per generated token because the latter includes extra prompt positions. Those denominators should not be mixed.')
heading(s,'Where performance is spent')
para(s,'The full-block trace issued 427,504,896 MAC operations. A single shared serial multiplier deliberately trades throughput for area. At most one datapath is active on one scheduled operation at a time; utilization percentages in the area section are spatial occupancy, not arithmetic duty cycle or achieved MAC efficiency.')
para(s,'External tensor storage keeps the silicon small but increases traffic. Commands, operand bytes and acknowledgments must be buffered and scheduled efficiently. A USB software round trip per operand would swamp core execution time. A bridge implementation and actual transport benchmark are still required; no board TPS or system energy-per-token is available.')
heading(s,'Demonstration scope')
para(s,'All-attention offload is the strongest supported LLM demonstration. A selected complete decoder block is an additional functional demonstration, with altered output quality. All-block inference requires better numerical treatment before it can be advertised as useful SmolLM2 execution. Increasing clock frequency alone cannot repair the quantization failure.')

s=section('Verification scope and reproducibility','What has passed, what remains open, and how to audit this report')
table(s,[['Check','Status / boundary'],['Detailed routing / antenna','Zero reported routing and antenna violations in saved run6.'],['Available KLayout rule deck','Zero reported items; not a claim that every foundry rule is implemented.'],['Layout versus schematic','Extracted circuit matches the reference netlist.'],['Power / ground connectivity','Checked connected in the physical feasibility flow.'],['Setup / hold','Positive at 10 MHz in three cell corners with nominal interconnect; conditional fmax sweep added here.'],['Power','Fresh vectorless estimate only; no fabricated or workload-measured power.'],['Official shuttle sign-off','Not established; reproduce in approved PDK/flow, with actual integration constraints.']], [0.35,0.65])
para(s,'Remaining work: resolve the TT extraction/reload timing difference; run complete RC/PVT/variation and pulse-width checks; recheck the 41.8 ps fast-corner hold margin; validate reset/interface behavior on the target board; characterize realistic switching and power integrity; enforce long-vector range safety; improve full-block quantization; and benchmark the external memory/bridge path.')
heading(s,'Evidence and exact artifacts')
para(s,'Area and physical checks: attention-extended/physical/run6/summary.json, instances.csv, GDS, routed database and SPEF. Fresh timing/power: report_ppa.tcl, report_ppa/results.json, per-corner logs and timing reports, and the isolated SS power log. Functional results: smol-rtl-test/*-results.json and comparison-results.json. The accompanying evidence ZIP contains these reports, scripts and the two prior detailed reports, not the full PDK, tool binaries or model weights.')
para(s,'Reproduce fresh PPA from the existing physical-study directory with PVT_CORNER set to tt_025C_1v80, ss_100C_1v60 or ff_n40C_1v95, then run ./openroad.sh -no_init -exit report_ppa.tcl. Run report_ss_power.tcl for the isolated SS alpha=0.2 estimate. These analyses read the fixed routed design; no placement or routing changes were made for this report.')
para(s,'GDS SHA-256: '+summary['gds_sha256'])
para(s,'RTL SHA-256: '+hashlib.sha256((R/'attention-extended/norm_odd.v').read_bytes()).hexdigest())
heading(s,'Primary technical references')
para(s,'OpenSTA command definitions: https://opensta.readthedocs.io/en/latest/Commands/ . OpenSTA power example: https://github.com/The-OpenROAD-Project/OpenSTA/blob/master/examples/power.tcl . Tiny Tapeout template: https://github.com/TinyTapeout/ttsky-verilog-template . SKY130 physical platform: https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/tree/master/flow/platforms/sky130hd . Local model file hashes and package versions are in the saved SmolLM2 provenance.json.')

styles=getSampleStyleSheet();styles.add(ParagraphStyle(name='BodyX',fontName='Helvetica',fontSize=9.5,leading=13.2,spaceAfter=9));styles.add(ParagraphStyle(name='CellX',fontName='Helvetica',fontSize=8.5,leading=11));styles.add(ParagraphStyle(name='HeadX',fontName='Helvetica-Bold',fontSize=13,leading=17,spaceBefore=8,spaceAfter=7));styles.add(ParagraphStyle(name='TitleX',fontName='Helvetica-Bold',fontSize=23,leading=27,spaceAfter=10));styles.add(ParagraphStyle(name='SubX',fontName='Helvetica',fontSize=10,leading=14,textColor=colors.HexColor('#527184'),spaceAfter=18))
esc=lambda t:html.escape(str(t))
story=[];md=['# ECE 298A: Single-tile attention accelerator\n\nFull engineering report - 25 September 2026\n']
for n,sec in enumerate(sections):
 if n:story.append(PageBreak())
 story.extend([Paragraph(f'{n+1:02d}  '+esc(sec['title']),styles['TitleX']),Paragraph(esc(sec['subtitle']),styles['SubX'])]);md.append('## '+sec['title']+'\n\n'+sec['subtitle']+'\n')
 for item in sec['items']:
  kind=item[0]
  if kind=='p':story.append(Paragraph(esc(item[1]),styles['BodyX']));md.append(item[1]+'\n')
  elif kind=='h':story.append(Paragraph(esc(item[1]),styles['HeadX']));md.append('### '+item[1]+'\n')
  elif kind=='table':
   rows=item[1];widths=item[2];w=499
   t=Table([[Paragraph(('<b>'+esc(c)+'</b>') if i==0 else esc(c),styles['CellX']) for c in row] for i,row in enumerate(rows)],colWidths=[w*x for x in widths] if widths else None,repeatRows=1,hAlign='LEFT')
   t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e3eef3')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),0.7,colors.HexColor('#648492')),('LINEBELOW',(0,1),(-1,-1),0.25,colors.HexColor('#cbd8df')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story.extend([t,Spacer(1,11)])
   md.extend(['| '+' | '.join(row)+' |' for row in rows[:1]]+['|'+'|'.join(['---']*len(rows[0]))+'|']+['| '+' | '.join(row)+' |' for row in rows[1:]]+[''])
  elif kind=='image':
   from PIL import Image as PI
   im=PI.open(item[1]);iw,ih=im.size;story.extend([Image(item[1],width=499,height=499*ih/iw),Spacer(1,8)]);md.append('![Actual layout](Attention-tile-layout.png)\n')
def footer(c,d):
 c.setStrokeColor(colors.HexColor('#a6bbc6'));c.line(48,42,547,42);c.setFont('Helvetica',8);c.setFillColor(colors.HexColor('#527184'));c.drawString(48,29,'ECE 298A  |  One-tile feasibility study  |  2026-09-25');c.drawRightString(547,29,str(d.page))
pdf=O/'ECE298A-Full-Engineering-Report.pdf';SimpleDocTemplate(str(pdf),pagesize=A4,rightMargin=48,leftMargin=48,topMargin=43,bottomMargin=56,title='ECE 298A Single-Tile Attention Accelerator - Full Engineering Report',author='ECE 298A project study').build(story,onFirstPage=footer,onLaterPages=footer)
(R/'ECE298A-Full-Engineering-Report.md').write_text('\n'.join(md))
paths=[R/'build_full_report.py',R/'ECE298A-Full-Engineering-Report.md',R/'Attention-tile-layout.png',R/'Attention-one-tile-physical-report.md',R/'SmolLM2-RTL-test-report.md',P/'report_ppa.tcl',P/'report_ss_power.tcl',P/'report_ss_power.log',P/'openroad.sh',P/'run6/summary.json',P/'run6/constraints.sdc',P/'run6/instances.csv',R/'attention-extended/norm_odd.v']+list((P/'report_ppa').glob('*'))+list(P.glob('report_ppa_*.log'))+list((R/'smol-rtl-test').glob('*results.json'))+[R/'smol-rtl-test/provenance.json']
with zipfile.ZipFile(R/'ECE298A-Report-Evidence.zip','w',zipfile.ZIP_DEFLATED) as z:
 for f in paths:z.write(f,f.relative_to(R))
print(pdf);print(json.dumps(ppa,indent=2))
