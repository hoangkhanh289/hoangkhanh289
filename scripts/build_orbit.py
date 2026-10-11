"""Build a standalone three-tier silicon solar system, including reduced motion."""
from pathlib import Path
from html import escape
import hashlib
import json
from copy import deepcopy
from functools import lru_cache
import math
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
WIDTH, HEIGHT = 1600, 1020
CX, CY, STEPS = 800, 510, 96
MCU_RX, MCU_RY, MCU_PERIOD = 520, 210, 96
VENDOR_RX, VENDOR_RY = 280, 115
TECH_RX, TECH_RY = 700, 360
CAMERA_PERIOD, CAMERA_STEP = 32, .5
COLORS = {'esp':'#FF6E59','st':'#38BDF8','nordic':'#00A9CE','pi':'#E21C55'}
LOGOS = {'esp':'espressif','st':'stmicroelectronics','nordic':'nordicsemiconductor','pi':'raspberrypi'}
# A rigid ten-slot ring: all nodes use the same angular clock, 36 degrees apart.
# Only local satellites have independent motion; MCU centers never drift.
MCUS = [
 ('p4','ESP32-P4','Dual RISC-V · 400MHz','esp',MCU_RX,MCU_RY,MCU_PERIOD,.05,('MIPI','H.264')),
 ('h743','STM32H743','M7 · 480MHz · FPU','st',MCU_RX,MCU_RY,MCU_PERIOD,.15,('RMII','USB HS')),
 ('rp2350','RP2350','2 cores · M33 / Hazard3','pi',MCU_RX,MCU_RY,MCU_PERIOD,.25,('PIO v2','Trust')),
 ('s3','ESP32-S3','LX7 · Vector DSP / OPI','esp',MCU_RX,MCU_RY,MCU_PERIOD,.35,('Vector','OPI')),
 ('g474','STM32G474','HRTIM · 184ps · FOC','st',MCU_RX,MCU_RY,MCU_PERIOD,.45,('HRTIM','FOC')),
 ('nrf5340','nRF5340','Dual M33 · LE Audio','nordic',MCU_RX,MCU_RY,MCU_PERIOD,.55,('Audio','Crypto')),
 ('c6','ESP32-C6','Wi-Fi 6 · Thread / Zigbee','esp',MCU_RX,MCU_RY,MCU_PERIOD,.65,('Wi-Fi 6','Mesh')),
 ('wb55','STM32WB55','M4 + M0+ · BLE / Thread','st',MCU_RX,MCU_RY,MCU_PERIOD,.75,('BLE','Thread')),
 ('nrf9160','nRF9160','LTE-M / NB-IoT · GNSS','nordic',MCU_RX,MCU_RY,MCU_PERIOD,.85,('LTE-M','GNSS')),
 ('rp2040','RP2040','Dual M0+ · 8× PIO','pi',MCU_RX,MCU_RY,MCU_PERIOD,.95,('PIO','DMA')),
]
PACKAGES = {
 'p4': ('qfn', 26, 32, 32, 'QFN104'),
 's3': ('qfn', 14, 32, 32, 'QFN56'),
 'c6': ('qfn', 10, 32, 32, 'QFN40'),
 'h743': ('lqfp', 25, 32, 32, 'LQFP100 · STM32H743VI'),
 'g474': ('lqfp', 16, 32, 32, 'LQFP64 · STM32G474RE'),
 'wb55': ('qfn', 17, 32, 32, 'VFQFPN68 · STM32WB55RG'),
 'rp2350': ('qfn', 15, 32, 32, 'QFN60 · RP2350A'),
 'rp2040': ('qfn', 14, 32, 32, 'QFN56'),
 # aQFN is a multi-row underside array; only simplified visible edge contacts.
 'nrf5340': ('aqfn', 12, 32, 32, 'aQFN94 · edge contacts simplified'),
 'nrf9160': ('lga', 10, 42, 27.6, 'LGA127 · 16 × 10.5mm SiP'),
}
VENDORS = [('esp','Espressif'),('st','STMicro'),('nordic','Nordic'),('pi','Raspberry Pi')]
# Capabilities of the whole ecosystem, not a claim that every chip supports every tag.
TECH = [
 ('wifi','Wi-Fi 6','802.11ax · TWT','#FF9279','rf'),
 ('ble','Bluetooth LE','5.4 / LE Audio','#7DD3FC','rf'),
 ('mesh','Thread / Matter','802.15.4 mesh','#5EEAD4','rf'),
 ('lora','LoRaWAN','Sub-1GHz RF module','#A5B4FC','rf'),
 ('cell','LTE-M / NB-IoT','Cellular · SIM / eSIM','#67E8F9','rf'),
 ('can','CAN-FD','5Mbps · Industrial','#FBBF77','bus'),
 ('usb','USB 2.0 HS','480Mbps · OTG','#7DD3FC','bus'),
 ('eth','Ethernet','10/100 · RMII / 1588','#6EE7B7','bus'),
 ('octal','Octal-SPI','DTR / HyperBus','#C4B5FD','bus'),
 ('mipi','MIPI CSI / DSI','Camera / Display','#F9A8D4','bus'),
 ('ai','Vector / TinyML','DSP · NPU Int8*','#FCA5A5','compute'),
 ('pio','PIO engines','Custom waveforms','#F9A8D4','compute'),
 ('timer','HRTIM','184ps · Precision PWM','#93C5FD','compute'),
 ('crypto','Hardware crypto','AES-256 / ECC / Boot','#5EEAD4','compute'),
]


def label(y, value, size, color='#E7F3FF', detail=False, x=0):
 return (f'<text x="{x}" y="{y}" text-anchor="middle" font-size="{size}" fill="{color}" '
         f'class="{"detail" if detail else "name"}" paint-order="stroke" stroke="#050914" '
         f'stroke-width="3" stroke-linejoin="round">{escape(value)}</text>')


def project(u,v,z=0):
 return u-v, .5*(u+v)-z


def polygon(points,fill,extra=''):
 coords=' '.join(f'{x:.3f},{y:.3f}' for x,y in (project(*p) for p in points))
 return f'<polygon points="{coords}" fill="{fill}" {extra}/>'


def semiconductor_core(height=1):
 """Exaggerated open semiconductor package with an exposed patterned silicon die."""
 def project(u,v,z=0):return u-v, .5*(u+v)-height*z
 def polygon(points,fill,extra=''):
  coords=' '.join(f'{x:.3f},{y:.3f}' for x,y in (project(*p) for p in points))
  return f'<polygon points="{coords}" fill="{fill}" {extra}/>'
 out=['''<linearGradient id="core-substrate" x2="1" y2="1"><stop stop-color="#325B4C"/><stop offset=".5" stop-color="#173C32"/><stop offset="1" stop-color="#0B2827"/></linearGradient>
 <linearGradient id="core-wafer" x2="1" y2="1"><stop stop-color="#8C7361"/><stop offset=".28" stop-color="#404B72"/><stop offset=".55" stop-color="#377C88"/><stop offset=".8" stop-color="#726D92"/><stop offset="1" stop-color="#B79265"/></linearGradient>
 <linearGradient id="core-solder" x2=".3" y2="1"><stop stop-color="#F1F1D9"/><stop offset=".28" stop-color="#B5C8C7"/><stop offset=".7" stop-color="#5B797F"/><stop offset="1" stop-color="#263E45"/></linearGradient>
 <g id="master-core" data-style="exposed-semiconductor"><title>Exposed silicon die, circuit floorplan, gold bond wires and BGA substrate</title>
 <g id="master-bga-balls" fill="url(#core-solder)" stroke="#456266" stroke-width=".7">''']
 for axis in (0,1):
  for i in range(16):
   p=-78+156*(i+.5)/16
   x,y=project(84,p,-23) if axis==0 else project(p,84,-23)
   out.append(f'<ellipse cx="{x:.3f}" cy="{y:.3f}" rx="4.4" ry="3.1"/>')
 out.append('</g><g id="core-substrate-stack">')
 for z,color in ((-10,'#0C211F'),(-5,'#284839'),(0,'url(#core-substrate)')):
  out.append(polygon([(-86,86,z),(86,86,z),(86,86,z-6),(-86,86,z-6)],color,'stroke="#608077" stroke-width=".7"'))
  out.append(polygon([(86,-86,z),(86,86,z),(86,86,z-6),(86,-86,z-6)],color,'stroke="#608077" stroke-width=".7"'))
 out += [polygon([(-86,-86,0),(86,-86,0),(86,86,0),(-86,86,0)],'url(#core-substrate)','stroke="#70958A" stroke-width="1.8"'),
         '<g transform="matrix(1 .5 -1 .5 0 0)" fill="none" stroke="#BAA16C" stroke-width="1" opacity=".8"><rect x="-80" y="-80" width="160" height="160"/>']
 for i in range(12):
  p=-48+96*i/11
  for sign in (-1,1):
   out.append(f'<path d="M{sign*80} {p}H{sign*74}V{p+3}H{sign*68} M{p} {sign*80}V{sign*74}H{p+3}V{sign*68}"/>')
 out.append('</g></g>')
 # A raised die-attach pedestal makes the package construction visible at README scale.
 for axis in (0,1):
  face=[(-70,70,26),(70,70,26),(70,70,0),(-70,70,0)] if axis==0 else [(70,-70,26),(70,70,26),(70,70,0),(70,-70,0)]
  out.append(polygon(face,'#18272C' if axis==0 else '#263B40','stroke="#809391" stroke-width="1"'))
 out.append(polygon([(-70,-70,26),(70,-70,26),(70,70,26),(-70,70,26)],'url(#metal)','stroke="#B6C9C3" stroke-width="1.2"'))
 def wires(near):
  result=['<g class="core-bond-wires" fill="none" stroke="url(#gold)" stroke-width="1.8" stroke-linecap="round">']
  sign=1 if near else -1
  for axis in (0,1):
   for i in range(12):
    p=-48+96*i/11
    a=project(sign*61,p,50) if axis==0 else project(p,sign*61,50)
    b=project(sign*79,p,1) if axis==0 else project(p,sign*79,1)
    result.append(f'<path d="M{a[0]:.3f} {a[1]:.3f}Q{(a[0]+b[0])/2:.3f} {min(a[1],b[1])-30:.3f} {b[0]:.3f} {b[1]:.3f}"/>')
    result.append(f'<ellipse cx="{b[0]:.3f}" cy="{b[1]:.3f}" rx="2.4" ry="1.4" fill="#D9BB77" stroke="none"/>')
  return ''.join(result)+'</g>'
 out.append(wires(False))
 out += ['<g id="core-silicon-die">',
         polygon([(-64,64,50),(64,64,50),(64,64,32),(-64,64,32)],'#172C3A','stroke="#7D9CA4" stroke-width="1.2"'),
         polygon([(64,-64,50),(64,64,50),(64,64,32),(64,-64,32)],'#284455','stroke="#7D9CA4" stroke-width="1.2"'),
         polygon([(-64,-64,50),(64,-64,50),(64,64,50),(-64,64,50)],'url(#core-wafer)','stroke="#C5CBBD" stroke-width="1.8"'),
         f'<g id="core-floorplan" transform="matrix(1 .5 -1 .5 0 {-50*height:.6f})">',
         '<rect x="-58" y="-58" width="116" height="116" fill="none" stroke="#E4D6AC" stroke-width="1.4"/>']
 # Regular SRAM arrays and four logic regions replace the oversized initials plaque.
 for x,y,w,h in [(-53,-53,28,46),(24,-53,29,46),(-53,10,28,43),(24,10,29,43)]:
  out.append(f'<g class="core-memory-bank"><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#203A4C" stroke="#B6C6AC" stroke-width=".8"/>')
  for row in range(6):
   for col in range(4):
    out.append(f'<rect x="{x+2+col*(w-4)/4:.2f}" y="{y+2+row*(h-4)/6:.2f}" width="{(w-4)/4-1.4:.2f}" height="{(h-4)/6-1.2:.2f}" fill="{"#BDB592" if row%2 else "#6CA8AA"}" opacity=".85"/>')
  out.append('</g>')
 for x,y in [(-18,-51),(3,-51),(-18,13),(3,13)]:
  out.append(f'<rect class="core-logic-block" x="{x}" y="{y}" width="15" height="38" fill="#4B6D7A" stroke="#E7CC9B" stroke-width=".8"/>')
  for line in range(5):out.append(f'<path d="M{x+2} {y+5+line*6}H{x+13}" stroke="#B6C9B6" stroke-width=".9"/>')
 out.append('<path d="M-54 0H54 M-21 -54V54 M21 -54V54 M0 -54V-9H-9V9H0V54" fill="none" stroke="#ECC992" stroke-width="2"/>')
 for axis in (0,1):
  for sign in (-1,1):
   for i in range(12):
    p=-48+96*i/11
    x,y=(sign*59,p) if axis==0 else (p,sign*59)
    out.append(f'<rect x="{x-1.6:.2f}" y="{y-1.6:.2f}" width="3.2" height="3.2" fill="#F3D69C"/>')
 out += ['</g></g>',wires(True),'</g>']
 return ''.join(out)


def camera_pose(time):
 """A slow forward pitch: the rear recedes as the foreground opens outward."""
 lean=math.sin(math.pi*time/CAMERA_PERIOD)**2
 return .92-.10*lean, .035+.105*lean, 18*lean


def camera_height(time):
 compression,_,_=camera_pose(time)
 # Preserve the projected height of vertical die walls while the plane pitches.
 return math.sqrt(1-(.5*compression)**2)/math.sqrt(.75)/compression


def camera_point(x,y,time):
 _,depth,_=camera_pose(time)
 perspective=1/(1-depth*y/TECH_RY)
 return x*perspective,y*perspective,perspective


@lru_cache(maxsize=None)
def timeline(period):
 count=round(period/CAMERA_STEP)
 return tuple(period*i/count for i in range(count+1))


def sampled_animation(attribute,values,period,transform=False):
 times=';'.join(f'{t/period:.8f}' for t in timeline(period))
 value=';'.join(values)
 tag='animateTransform' if transform else 'animate'
 kind=f' type="{attribute}" attributeName="transform"' if transform else f' attributeName="{attribute}"'
 return f'<{tag}{kind} values="{value}" keyTimes="{times}" dur="{period}s" begin="0s" calcMode="linear" repeatCount="indefinite"/>'


def billboard(content,animated=True):
 values=[f'{1/.94:.7f} {1/camera_pose(t)[0]:.7f}' for t in timeline(CAMERA_PERIOD)]
 motion=sampled_animation('scale',values,CAMERA_PERIOD,True) if animated else ''
 return f'<g class="camera-billboard" transform="scale({values[0]})">{motion}{content}</g>'


def depth_position(content,rx,ry,period,phase,reverse=False,shading=False,animated=True):
 duration=math.lcm(period,CAMERA_PERIOD)
 positions=[];scales=[];shades=[]
 for t in timeline(duration):
  a=2*math.pi*(t/period+phase)*(-1 if reverse else 1)
  x,y=rx*math.cos(a),ry*math.sin(a)
  px,py,p=camera_point(x,y,t)
  positions.append(f'{px-x:.5f} {py-y:.5f}')
  scales.append(f'{p:.7f}')
  shades.append(f'{.9+.1*math.sin(a):.6f}')
 shade=sampled_animation('opacity',shades,duration) if shading and animated else ''
 translate=sampled_animation('translate',positions,duration,True) if animated else ''
 scale=sampled_animation('scale',scales,duration,True) if animated else ''
 return (f'<g class="depth-position" data-rx="{rx}" data-ry="{ry}" data-phase="{phase}" data-reverse="{int(reverse)}" transform="translate({positions[0]})">'
         f'{translate}<g class="depth-scale" transform="scale({scales[0]})">{scale}{shade}{content}</g></g>')


def tilted_core():
 """Morph authored geometry, compensating height independently of the pitched plane."""
 states=[]
 for t in timeline(CAMERA_PERIOD):
  root=ET.fromstring('<svg>'+semiconductor_core(camera_height(t))+'</svg>')
  states.append(root.find('.//*[@id="master-core"]'))
 result=deepcopy(states[0]);result.set('id','master-core-tilt')
 targets=list(result.iter());sources=[list(s.iter()) for s in states]
 for i,node in enumerate(targets):
  if i and node.get('id'):node.set('id','tilted-'+node.get('id'))
  for attr in ('points','d','cx','cy','transform'):
   values=[s[i].get(attr) for s in sources]
   if values[0] is None or len(set(values))==1:continue
   if attr=='transform':
    # The die floorplan is an affine plane; only its vertical height changes.
    base=float(values[0].split()[-1].rstrip(')'))
    offsets=[f'0 {float(v.split()[-1].rstrip(")"))-base:.6f}' for v in values]
    wrapper=ET.Element('g',{'class':'core-height-plane'})
    wrapper.append(ET.fromstring(sampled_animation('translate',offsets,CAMERA_PERIOD,True)))
    parent=next(p for p in result.iter() if node in list(p))
    index=list(parent).index(node);parent.remove(node);parent.insert(index,wrapper);wrapper.append(node)
   else:node.append(ET.fromstring(sampled_animation(attr,values,CAMERA_PERIOD)))
 return ET.tostring(result,encoding='unicode')


def package_contacts(kind,count,hu,hv):
 parts=[]
 if kind=='lqfp':
  # Four real gull-wing banks. A strip rises from the body, bends down,
  # then forms a flat solder foot; rear roots are occluded by the body.
  for axis in (0,1):
   h,span=(hu,hv) if axis==0 else (hv,hu)
   for sign in (-1,1):
    for n in range(count):
     p=-span+4+(2*span-8)*(n+.5)/count
     half=(2*span-8)/count*.26
     strip=[(h,5),(h+5,4.5),(h+8,1),(h+13,1)]
     def vertex(d,side,z):
      return (sign*d,side,z) if axis==0 else (side,sign*d,z)
     points=[vertex(d,p-half,z) for d,z in strip]+[vertex(d,p+half,z) for d,z in reversed(strip)]
     parts.append(polygon(points,'#9BA9B6','class="gull-wing-lead" stroke="#34485B" stroke-width=".35"'))
     a,b=project(*vertex(h+8,p,1.3)),project(*vertex(h+13,p,1.3))
     parts.append(f'<path d="M{a[0]:.3f} {a[1]:.3f}L{b[0]:.3f} {b[1]:.3f}" stroke="#D3DFE8" stroke-width=".55"/>')
 else:
  # Only the two near edges are visible. QFN contacts finish at the
  # sidewall; LGA lands stay under the package, with no fabricated leads.
  for axis in (0,1):
   h,span=(hu,hv) if axis==0 else (hv,hu)
   for n in range(count):
    p=-span+3+(2*span-6)*(n+.5)/count
    half=(2*span-6)/count*.29
    def vertex(d,side,z):
     return (d,side,z) if axis==0 else (side,d,z)
    if kind!='lga':
     parts.append(polygon([vertex(h,p-half,0),vertex(h,p+half,0),vertex(h,p+half,3),vertex(h,p-half,3)],'#AAB8C3','class="side-contact"'))
    else:
     parts.append(polygon([vertex(h-.8,p-half,-.4),vertex(h+.25,p-half,-.4),vertex(h+.25,p+half,-.4),vertex(h-.8,p+half,-.4)],'url(#gold)','class="underside-land"'))
 return ''.join(parts)


@lru_cache(maxsize=1)
def energy_contours():
 """Load baked outlines and reject stale geometry when original logo paths change."""
 data=json.loads(Path(__file__).with_name('logo-energy-contours.json').read_text(encoding='utf-8'))['brands']
 materials=ET.parse(Path(__file__).with_name('orbit-materials.svg')).getroot()
 for brand,record in data.items():
  logo=materials.find(f'.//*[@id="logo-{LOGOS[brand]}"]')
  paths='\n'.join(n.get('d') for n in logo.iter(f'{{{NS}}}path'))
  if hashlib.sha256(paths.encode()).hexdigest()!=record['source_sha256']:
   raise ValueError('Logo outlines changed; run scripts/build_logo_contours.cjs before rebuilding')
 return data


def energy_volume(brand, timing=None, lift=12):
 """Extrude the brand's actual compound outline, including its negative spaces."""
 color,logo=COLORS[brand],LOGOS[brand]
 contours=energy_contours()[brand]['contours']
 def at(point,z):return project((point[0]-12)*1.5,(point[1]-12)*1.5,z)
 def walls(side,height):
  pieces=[]
  for contour in contours:
   pts=contour['points']
   for i,kind in enumerate(contour['sides']):
    if kind!=side:continue
    a,b=pts[i],pts[(i+1)%len(pts)]
    vertices=[at(a,0),at(b,0),at(b,7+height),at(a,7+height)]
    pieces.append('M'+'L'.join(f'{x:.3f} {y:.3f}' for x,y in vertices)+'Z')
  return ''.join(pieces)
 out=[f'<g class="energy-volume" data-logo="{logo}" data-bottom-z="0" data-lid-z="7">',
      f'<g transform="matrix(1.5 .75 -1.5 .75 0 0)" color="{color}" opacity=".18"><use class="energy-volume-base" href="#logo-{logo}"/></g>']
 for side,fill,opacity in [('back',color,.05),('left',f'url(#energy-face-left-{brand})',1),('right',f'url(#energy-face-right-{brand})',1)]:
  out.append(f'<path class="energy-contour-wall energy-volume-{side}" d="{walls(side,lift)}" fill="{fill}" fill-opacity="{opacity}">')
  if timing:out.append(f'<animate attributeName="d" values="{walls(side,2)};{walls(side,24)};{walls(side,2)}" {timing}/>')
  out.append('</path>')
 # Sparse light columns follow curved outer boundaries and inner cutouts.
 columns=[]
 for contour in contours:
  last=None
  for point,side in zip(contour['points'],contour['sides']):
   if side not in ('left','right'):continue
   if last is None or math.dist(point,last)>=2.6:columns.append(point);last=point
 def pillars(height):
  return ''.join(f'M{at(p,0)[0]:.3f} {at(p,0)[1]:.3f}V{at(p,7+height)[1]:.3f}' for p in columns)
 out.append(f'<path class="energy-columns" data-column-count="{len(columns)}" d="{pillars(lift)}" fill="none" stroke="{color}" stroke-width=".7" stroke-opacity=".55">')
 if timing:out.append(f'<animate attributeName="d" values="{pillars(2)};{pillars(24)};{pillars(2)}" {timing}/>')
 out+=['</path></g>']
 return ''.join(out)


def chip_logo_energy(key, brand):
 """A luminous brand mark levitates vertically above a fixed package socket."""
 color,logo=COLORS[brand],LOGOS[brand]
 phase=-next(i for i,row in enumerate(MCUS) if row[0]==key)*.37
 timing=f'dur="4.8s" begin="{phase:.2f}s" repeatCount="indefinite" keyTimes="0;.5;1" calcMode="spline" keySplines=".45 0 .55 1;.45 0 .55 1"'
 mark=f'<g transform="matrix(1.5 .75 -1.5 .75 0 -7)" color="{color}"><use class="energy-brand-mark energy-volume-cap" href="#logo-{logo}" filter="url(#energy-logo-glow)"/></g>'
 socket=f'<g transform="matrix(1.5 .75 -1.5 .75 0 0)" color="{color}"><use href="#logo-{logo}" filter="url(#energy-logo-glow)"/></g>'
 return f'''<g id="energy-{key}" class="chip-energy-core" data-brand="{brand}">
 <g transform="matrix(1.5 .75 -1.5 .75 0 -7)" color="#030B16"><use class="energy-lid-opening" href="#logo-{logo}"/></g>
 <g class="motion-only">
 <g class="energy-socket-glow" opacity=".3"><animate attributeName="opacity" values=".3;.95;.3" {timing}/>{socket}</g>
 {energy_volume(brand,timing,2)}
 <g class="energy-logo-lift" transform="translate(0 -2)"><animateTransform attributeName="transform" type="translate" values="0 -2;0 -24;0 -2" {timing}/>
 <g class="energy-logo-light" opacity=".7"><animate attributeName="opacity" values=".7;1;.7" {timing}/>{mark}</g></g>
 </g>
 <g class="still-only"><g opacity=".45">{socket}</g>{energy_volume(brand)}<g transform="translate(0 -12)">{mark}</g></g>
 </g>'''


def chip(row):
 key,name,spec,brand,*_=row
 color,logo=COLORS[brand],LOGOS[brand]
 kind,count,hu,hv,package=PACKAGES[key]
 out=[f'<g id="chip-{key}" data-package="{kind}"><title>{escape(name+" · "+spec+" · "+package)}</title>',
      f'<ellipse cy="{(hu+hv)*.5+8:.3f}" rx="{hu+hv+7}" ry="11" fill="#00040B" opacity=".65"/>']
 contacts=package_contacts(kind,count,hu,hv)
 if kind=='lqfp':out.append(contacts)
 out += [polygon([(-hu,hv,7),(hu,hv,7),(hu,hv,0),(-hu,hv,0)],'#07101B','stroke="#293C4D" stroke-width=".6"'),
         polygon([(hu,-hv,7),(hu,hv,7),(hu,hv,0),(hu,-hv,0)],'#101C2A','stroke="#293C4D" stroke-width=".6"')]
 if kind!='lqfp':out.append(contacts)
 out += [polygon([(-hu,-hv,7),(hu,-hv,7),(hu,hv,7),(-hu,hv,7)],'url(#silicon)',f'stroke="{color}" stroke-opacity=".65" stroke-width=".8"'),
         polygon([(-hu+2,-hv+2,7.1),(hu-2,-hv+2,7.1),(hu-2,hv-2,7.1),(-hu+2,hv-2,7.1)],'#101A27','stroke="#466078" stroke-opacity=".5" stroke-width=".5"'),
         chip_logo_energy(key,brand)]
 x,y=project(-hu+6,-hv+6,7.3)
 out += [f'<ellipse cx="{x:.3f}" cy="{y:.3f}" rx="2" ry="1" fill="#9BB0C3" opacity=".8"/>',
         f'</g><g id="label-{key}">{label(0,name,27)}{label(24,spec,20,color,True)}</g>']
 return ''.join(out)


def icon(category):
 if category=='rf':return '<path d="M-9 1Q0 -9 9 1M-6 4Q0 -3 6 4M-3 7Q0 3 3 7"/><circle cy="10" r="1.5" fill="currentColor"/>'
 if category=='bus':return '<path d="M-10 -6H-4L4 6H10M-10 6H-4L4 -6H10"/><circle cx="-10" cy="-6" r="2"/><circle cx="10" cy="6" r="2"/>'
 return '<rect x="-7" y="-7" width="14" height="14" rx="2"/><path d="M-3 -11V-7M3 -11V-7M-3 7V11M3 7V11M-11 -3H-7M7 3H11"/>'


def tech_capsule(row):
 key,name,spec,color,category=row
 size=min(23,190/(len(name)*.56))
 return f'''<g id="tech-{key}"><title>{escape(name+' · '+spec)}</title>
 <path d="M-100 -35H86L100 -21V21L86 35H-86L-100 21Z" fill="url(#glass)" stroke="{color}" stroke-opacity=".65"/>
 <path d="M-87 -33H85L98 -20" fill="none" stroke="{color}" stroke-opacity=".7"/>
 <g transform="translate(0 -35) scale(.6)" color="{color}" stroke="currentColor" stroke-width="1.7" fill="none">{icon(category)}</g>
 {label(-5,name,round(size,2),color)}{label(22,spec,18,'#C1D6E9',True)}</g>'''


def vendor_station(row):
 brand,name=row
 color=COLORS[brand]
 full={'esp':'Espressif Systems','st':'STMicroelectronics','nordic':'Nordic Semiconductor','pi':'Raspberry Pi'}[brand]
 return f'''<g id="station-{brand}"><title>{full}</title>
 <path d="M-99 -28H84L99 -13V17L84 32H-84L-99 17Z" fill="#030916" stroke="#254A64" stroke-width="2"/>
 <path d="M-99 -32H84L99 -17V13L84 28H-84L-99 13Z" fill="url(#glass)" stroke="{color}" stroke-opacity=".9"/>
 <path d="M-82 -30H80" stroke="{color}" stroke-width="2"/>
 <g transform="translate(-69 -3) scale(1.6)" color="{color}"><use href="#logo-{LOGOS[brand]}"/></g>
 {label(5,name,20 if brand=='pi' else 24,color,x=26)}</g>'''


def orbit_outline(rx,ry,time):
 coords=[]
 for i in range(128):
  a=2*math.pi*i/128
  x,y,_=camera_point(rx*math.cos(a),ry*math.sin(a),time)
  coords.append(f'{CX+x:.3f} {CY+y:.3f}')
 return 'M'+'L'.join(coords)+'Z'


def orbit_paths(key,rx,ry):
 values=[orbit_outline(rx,ry,t) for t in timeline(CAMERA_PERIOD)]
 return (f'<path id="{key}" d="{values[0]}">{sampled_animation("d",values,CAMERA_PERIOD)}</path>'
         f'<path id="{key}-still" d="{values[0]}"/>')


def orbit_rail(key,style):
 return (f'<use class="motion-only" href="#{key}" {style}/>'
         f'<use class="still-only" href="#{key}-still" {style}/>')


def laser_links():
 out=['<g class="motion-only" id="laser-links">']
 for i,row in enumerate(MCUS):
  key,_,_,brand,rx,ry,period,phase,_=row
  values=[]
  for t in timeline(period):
   a=2*math.pi*(t/period+phase)
   x,y,_=camera_point(rx*math.cos(a),ry*math.sin(a),t)
   tx,ty,_=camera_point(TECH_RX*math.cos(a),TECH_RY*math.sin(a),t)
   values.append(f'M{CX+x:.4f} {CY+y:.4f}L{CX+tx:.4f} {CY+ty:.4f}')
  out.append(f'<path id="link-{key}" d="{values[0]}" fill="none">{sampled_animation("d",values,period)}</path>')
  out.append(f'<use href="#link-{key}" stroke="{COLORS[brand]}" stroke-opacity=".16"/>')
  out.append(f'<use href="#link-{key}" stroke="{COLORS[brand]}" stroke-opacity=".65" stroke-width="2" stroke-dasharray="15 210"><animate attributeName="stroke-dashoffset" values="210;-210" dur="{2.4+i*.18:.2f}s" repeatCount="indefinite"/></use>')
 return ''.join(out)+'</g>'


def layer_gate(period,phase,front,reverse=False):
 visible='1;0;1' if front!=reverse else '0;1;0'
 return (f'<animate attributeName="opacity" values="{visible}" keyTimes="0;.5;1" calcMode="discrete" '
         f'dur="{period}s" begin="-{period*phase:.4f}s" repeatCount="indefinite"/>')


def satellites(row,i,animated=True):
 key,_,_,brand,_,_,_,_,tags=row
 color,period=COLORS[brand],9+i*.7
 parts=[f'<g class="epicycles" data-parent="{key}"><ellipse rx="88" ry="30" fill="none" stroke="{color}" stroke-opacity=".27"/></g>']
 for j,tag in enumerate(tags):
  parts.append('<g class="satellite">' if animated else f'<g class="satellite" transform="translate({88 if j==0 else -88} 0)">')
  if animated:
   # Motion with rotate=0 keeps capsule text upright without script/counter-rotation.
   parts.append(f'<animateMotion path="M88 0A88 30 0 1 1 -88 0A88 30 0 1 1 88 0" dur="{period:.1f}s" begin="-{j*period/2:.3f}s" repeatCount="indefinite" rotate="0" calcMode="paced"/>')
  parts.append(f'<path d="M-29 -12H29V12H-29Z" fill="#061325" stroke="{color}" stroke-opacity=".7"/><text y="5" text-anchor="middle" font-size="14" font-weight="700" fill="{color}">{escape(tag)}</text></g>')
 return ''.join(parts)


def mcu_instance(row,i,front,animated=True):
 key,_,_,brand,rx,ry,period,phase,_=row
 side='front' if front else 'back'
 angle=2*math.pi*phase
 if not animated:
  scale=.975+.275*math.sin(angle)
  assembly=(f'<g transform="scale({scale:.4f})"><use href="#chip-{key}" transform="scale(.9)"/>{satellites(row,i,False)}</g>'
            +billboard(f'<use href="#label-{key}" transform="translate(0 {64 if front else -64})"/>',False))
  return (f'<g transform="translate({CX+rx*math.cos(angle):.3f} {CY+ry*math.sin(angle):.3f})">'
          +depth_position(assembly,rx,ry,period,phase,animated=False)+'</g>')
 times=';'.join(f'{n/STEPS:.8f}' for n in range(STEPS+1))
 scales=';'.join(f'{.975+.275*math.sin(2*math.pi*n/STEPS):.4f}' for n in range(STEPS+1))
 shades=';'.join(f'{.85+.15*math.sin(2*math.pi*n/STEPS):.4f}' for n in range(STEPS+1))
 begin=f'-{period*phase:.4f}s'
 # Rotate in the circular orbit plane, then project into the ellipse.
 # Counter-rotation and inverse projection keep chips/text upright.
 # Identical linear clocks preserve each 36-degree offset exactly.
 degrees=360*phase
 name=billboard(f'<use class="mcu-label" href="#label-{key}" transform="translate(0 {64 if front else -64})"/>')
 assembly=f'''<g class="mcu-assembly"><g class="mcu-perspective"><animateTransform attributeName="transform" type="scale" values="{scales}" keyTimes="{times}" dur="{period}s" begin="{begin}" repeatCount="indefinite"/>
 <animate attributeName="opacity" values="{shades}" keyTimes="{times}" dur="{period}s" begin="{begin}" repeatCount="indefinite"/>
 <use href="#chip-{key}" transform="scale(.9)"/>{satellites(row,i)}</g>{name}</g>'''
 content=depth_position(assembly,rx,ry,period,phase)
 return f'''<g id="mcu-{key}-{side}" class="mcu-instance" data-period="{period}" opacity="0">
 {layer_gate(period,phase,front)}
 <g transform="translate({CX} {CY})"><g transform="scale(1 {ry/rx:.10f})">
 <g class="mcu-ring-rotation" transform="rotate({degrees:.6f})"><animateTransform attributeName="transform" type="rotate" from="{degrees:.6f}" to="{degrees+360:.6f}" dur="{period}s" begin="0s" calcMode="linear" repeatCount="indefinite"/>
 <g transform="translate({rx} 0)"><g transform="rotate({-degrees:.6f})"><animateTransform attributeName="transform" type="rotate" from="{-degrees:.6f}" to="{-degrees-360:.6f}" dur="{period}s" begin="0s" calcMode="linear" repeatCount="indefinite"/>
 <g class="mcu-position" transform="scale(1 {rx/ry:.10f})">
 {content}</g></g></g></g></g></g></g>'''


def tier_instance(row,i,front,kind,animated=True):
 reverse=kind=='technology'
 rx,ry,period=(TECH_RX,TECH_RY,112) if reverse else (VENDOR_RX,VENDOR_RY,96)
 count=len(TECH) if reverse else len(VENDORS)
 phase=(i+.5)/count
 symbol='tech-'+row[0] if reverse else 'station-'+row[0]
 side='front' if front else 'back'
 face=f'<use class="tier-card" data-face="{"orbit-plane" if reverse else "camera"}" href="#{symbol}"/>'
 # Functional cards belong to the pitched outer plane; vendor stations face the camera.
 if not reverse:face=billboard(face,animated)
 if not animated:
  a=2*math.pi*phase*(-1 if reverse else 1)
  content=depth_position(face,rx,ry,period,phase,reverse,animated=False)
  return f'<g transform="translate({CX+rx*math.cos(a):.3f} {CY+ry*math.sin(a):.3f})">{content}</g>'
 degrees=360*phase*(-1 if reverse else 1);turn=-360 if reverse else 360
 content=depth_position(face,rx,ry,period,phase,reverse,True)
 return f'''<g id="{kind}-{row[0]}-{side}" data-period="{period}" opacity="0">{layer_gate(period,phase,front,reverse)}
 <g transform="translate({CX} {CY})"><g transform="scale(1 {ry/rx:.10f})"><g class="tier-ring-rotation" transform="rotate({degrees:.7f})">
 <animateTransform attributeName="transform" type="rotate" from="{degrees:.7f}" to="{degrees+turn:.7f}" dur="{period}s" begin="0s" calcMode="linear" repeatCount="indefinite"/>
 <g transform="translate({rx} 0)"><g transform="rotate({-degrees:.7f})">
 <animateTransform attributeName="transform" type="rotate" from="{-degrees:.7f}" to="{-degrees-turn:.7f}" dur="{period}s" begin="0s" calcMode="linear" repeatCount="indefinite"/>
 <g class="tier-position" transform="scale(1 {rx/ry:.10f})">{content}</g></g></g></g></g></g></g>'''


def build():
 materials=ET.parse(Path(__file__).with_name('orbit-materials.svg')).getroot().find(f'{{{NS}}}defs')
 out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title description">',
 '''<title id="title">Hoang Khanh · Multi-tier silicon solar system</title>
 <desc id="description">Exaggerated exposed semiconductor package with a patterned silicon die, gold bond wires, layered green substrate and silver BGA balls, four vendors, ten MCU and SoC models locked to a rigid rotating ring, and fourteen counter-rotating technology capsules. Layer-two chip centers stay 36 degrees apart and rotate at the same constant 3.75 degrees per second, completing a lap in 96 seconds. Circular-plane rotation starts from a 520 by 210 ellipse. A shared 32-second forward pitch gradually settles the core and all three rings; perspective expands the foreground and recedes the rear. Counter-rotation keeps MCU labels and vendor stations facing the camera. Functional cards on the outer ring follow the same plane pitch as the core and rings, including perspective compression. The die retains its vertical thickness as its top plane tilts. No independent chip drift or overtaking occurs. Brand logos rise and sink atop translucent energy volumes shaped to their original outlines, including inner cutouts, connected from the package underside through matching openings in the lid. Their shaded contour walls, boundary light columns and logo-shaped caps extend continuously with the logo, glowing in their vendor colors on a 4.8-second energy cycle. Local satellites retain separate motion. QFN side contacts, LQFP gull-wing leads and underside LGA lands replace generic pins. The outer belt represents ecosystem capabilities rather than features of every chip. A static composition is provided for reduced motion.</desc>
 <style>text{font-family:Consolas,"Liberation Mono",monospace}.name{font-weight:700}.detail{font-family:"Segoe UI",Arial,sans-serif;font-weight:500}.still-only{display:none}@media(prefers-reduced-motion:reduce){.motion-only{display:none}.still-only{display:inline}#stage-tilt{transform:scale(.94,.92)}#stage-settle{transform:translate(0px,0px)}}</style><defs>''']
 out.extend(ET.tostring(e,encoding='unicode') for e in materials)
 out.append(semiconductor_core(camera_height(0)))
 out.append(tilted_core())
 out.append('''<filter id="energy-logo-glow" x="-65%" y="-65%" width="230%" height="230%" color-interpolation-filters="sRGB"><feGaussianBlur in="SourceGraphic" stdDeviation="2.2" result="halo"/><feGaussianBlur in="SourceGraphic" stdDeviation=".8" result="light"/><feMerge><feMergeNode in="halo"/><feMergeNode in="light"/><feMergeNode in="SourceGraphic"/></feMerge></filter>''')
 for brand,color in COLORS.items():
  out.append(f'<linearGradient id="energy-face-left-{brand}" x2="1" y2="1"><stop stop-color="#E4F8FF" stop-opacity=".19"/><stop offset=".35" stop-color="{color}" stop-opacity=".3"/><stop offset="1" stop-color="{color}" stop-opacity=".06"/></linearGradient>')
  out.append(f'<linearGradient id="energy-face-right-{brand}" x2="0" y2="1"><stop stop-color="{color}" stop-opacity=".48"/><stop offset=".6" stop-color="{color}" stop-opacity=".23"/><stop offset="1" stop-color="{color}" stop-opacity=".1"/></linearGradient>')
 out.append('''<linearGradient id="glass" x2="0" y2="1"><stop stop-color="#13253B"/><stop offset=".45" stop-color="#091428"/><stop offset="1" stop-color="#030815"/></linearGradient>
 <linearGradient id="belt"><stop stop-color="#FF6E59"/><stop offset=".3" stop-color="#38BDF8"/><stop offset=".7" stop-color="#00A9CE"/><stop offset="1" stop-color="#E21C55"/></linearGradient>
 <clipPath id="frame"><rect x="1" y="1" width="1598" height="1018" rx="26"/></clipPath>
 <path id="trace-west" d="M0 510H80L120 550H200L250 600H360"/><path id="trace-east" d="M1600 510H1520L1480 550H1400L1350 600H1240"/>''')
 for key,rx,ry in [('vendor-orbit',VENDOR_RX,VENDOR_RY),('mcu-orbit',MCU_RX,MCU_RY),('technology-orbit',TECH_RX,TECH_RY),('outer-halo',712,373)]:
  out.append(orbit_paths(key,rx,ry))
 for row in MCUS:out.append(chip(row))
 out.extend(vendor_station(r) for r in VENDORS)
 out.extend(tech_capsule(r) for r in TECH)
 out.append('''</defs><g clip-path="url(#frame)">
 <rect width="1600" height="1020" fill="#050914"/><rect width="1600" height="1020" fill="url(#space)"/>
 <rect width="1600" height="1020" fill="url(#pcb-grid)" opacity=".28"/>
 <ellipse cx="800" cy="510" rx="740" ry="430" fill="url(#aura)"/>
 <g fill="none" stroke="#254557" stroke-opacity=".45"><path d="M36 90V36H160M1440 36H1564V90M36 930V984H160M1440 984H1564V930"/>
 <path d="M80 120H265L300 155H410M1520 120H1335L1300 155H1190M80 900H265L300 865H410M1520 900H1335L1300 865H1190"/>
 <use href="#trace-west"/><use href="#trace-east"/></g>
 <g class="motion-only" fill="none" stroke="#4ACBDC" stroke-width="2"><use href="#trace-west" stroke-dasharray="18 430"><animate attributeName="stroke-dashoffset" values="430;-430" dur="6s" repeatCount="indefinite"/></use>
 <use href="#trace-east" stroke-dasharray="18 430"><animate attributeName="stroke-dashoffset" values="430;-430" dur="6s" begin="-3s" repeatCount="indefinite"/></use></g>
 <text x="800" y="49" text-anchor="middle" font-size="36" letter-spacing="4" class="name" fill="#E4F4FF">HOANG KHANH</text>
 <text x="800" y="82" text-anchor="middle" font-size="24" letter-spacing="1.5" fill="#83BACF">SILICON SYSTEMS · MCU / SoC</text>''')
 for i in range(22):
  x,y=70+(i*239)%1460,146+(i*137)%720
  out.append(f'<circle cx="{x}" cy="{y}" r="5" fill="none" stroke="#BA8753" stroke-opacity=".22"/><circle cx="{x}" cy="{y}" r="1.5" fill="#997A51" opacity=".3"/>')
 for i in range(16):
  x,y=100+(i*167)%1400,130+(i*83)%760
  out.append(f'<g class="motion-only"><circle cx="{x}" cy="{y}" r="1.6" fill="#8FDCED" opacity=".3"><animate attributeName="cy" values="{y};{y-12};{y}" dur="{7+i*.3:.1f}s" repeatCount="indefinite"/><animate attributeName="opacity" values=".12;.5;.12" dur="{5+i*.2:.1f}s" repeatCount="indefinite"/></circle></g>')
 scales=[f'.94 {camera_pose(t)[0]:.7f}' for t in timeline(CAMERA_PERIOD)]
 drops=[f'0 {camera_pose(t)[2]:.7f}' for t in timeline(CAMERA_PERIOD)]
 out.append(f'<g id="perspective-stage" data-camera-period="{CAMERA_PERIOD}" transform="translate({CX} {CY})"><g id="stage-settle" transform="translate({drops[0]})">{sampled_animation("translate",drops,CAMERA_PERIOD,True)}<g id="stage-tilt" transform="scale({scales[0]})">{sampled_animation("scale",scales,CAMERA_PERIOD,True)}<g transform="translate({-CX} {-CY})">')
 for key,style in [('mcu-orbit','stroke="#365B7A" stroke-opacity=".5" stroke-dasharray="2 12"'),('technology-orbit','stroke="#12263D" stroke-width="9"'),('technology-orbit','stroke="url(#belt)" stroke-width="1.5" stroke-opacity=".6"'),('outer-halo','stroke="#5078A1" stroke-opacity=".22" stroke-dasharray="1 11"'),('vendor-orbit','stroke="#1A354A" stroke-width="5"'),('vendor-orbit','stroke="#55CDE3" stroke-opacity=".55"')]:
  out.append(orbit_rail(key,'fill="none" '+style))
 out.append('''<ellipse cx="800" cy="551" rx="174" ry="53" fill="#010711" stroke="#297C99"/><ellipse cx="800" cy="551" rx="154" ry="43" fill="url(#aura)" stroke="#5ADCE9" stroke-opacity=".4"/>
 <g class="motion-only" fill="none" stroke="#5ADCE9">''')
 for phase in [0,-2,-4]:out.append(f'<ellipse cx="800" cy="551" rx="100" ry="30"><animate attributeName="rx" values="100;220" dur="6s" begin="{phase}s" repeatCount="indefinite"/><animate attributeName="ry" values="30;72" dur="6s" begin="{phase}s" repeatCount="indefinite"/><animate attributeName="opacity" values=".45;0" dur="6s" begin="{phase}s" repeatCount="indefinite"/></ellipse>')
 out.append('</g>')
 out.append(laser_links())
 # Synchronized half-orbit copies emulate dynamic depth without DOM reordering.
 for front in (False,True):
  side='front' if front else 'back'
  out.append(f'<g class="motion-only" id="tiers-{side}">')
  for i,row in enumerate(TECH):out.append(tier_instance(row,i,front,'technology'))
  for i,row in enumerate(MCUS):out.append(mcu_instance(row,i,front))
  for i,row in enumerate(VENDORS):out.append(tier_instance(row,i,front,'vendor'))
  out.append('</g>')
  out.append(f'<g class="still-only" id="static-{side}">')
  for i,row in enumerate(TECH):
   if (((i+.5)/len(TECH))>.5)==front:out.append(tier_instance(row,i,front,'technology',False))
  for i,row in enumerate(MCUS):
   if (math.sin(2*math.pi*row[7])>=0)==front:out.append(mcu_instance(row,i,front,False))
  for i,row in enumerate(VENDORS):
   if (((i+.5)/len(VENDORS))<.5)==front:out.append(tier_instance(row,i,front,'vendor',False))
  out.append('</g>')
  if not front:out.append('''<g id="silicon-core" transform="translate(800 510)"><g class="motion-only"><animateTransform attributeName="transform" type="translate" values="0 0;0 -9;0 0" dur="6.5s" repeatCount="indefinite"/><use href="#master-core-tilt"/></g><use class="still-only" href="#master-core"/></g>
 ''')
 out.append('</g></g></g></g>')
 out.append('''<g fill="#AFCBDD" class="detail" font-size="22" text-anchor="middle"><text x="345" y="950">RF / WIRELESS</text><text x="800" y="950">HIGH-SPEED BUSES</text><text x="1255" y="950">COMPUTE / CONTROL</text></g>
 <path d="M195 968H1405" stroke="#224054"/><text x="800" y="995" text-anchor="middle" font-size="19" class="detail" fill="#7DA1B8">Ecosystem capabilities · * External accelerators / RF modules where required</text>
 </g><rect x="1" y="1" width="1598" height="1018" rx="26" fill="none" stroke="#244659" stroke-width="1.5"/></svg>''')
 path=ROOT/'assets/orbit.svg'
 path.write_text('\n'.join(line.rstrip() for line in '\n'.join(out).splitlines())+'\n',encoding='utf-8',newline='\n')
 md=ROOT/'README.md'
 digest=hashlib.sha256(path.read_bytes()).hexdigest()[:12]
 content=re.sub(r'(assets/orbit\.svg)\?v=[\da-f]+',rf'\1?v={digest}',md.read_text(encoding='utf-8'))
 content=re.sub(r'(?<=alt=")Hoang Khanh — [^"]*','Hoang Khanh — Silicon solar system with an exaggerated exposed semiconductor core, gold bond wires and patterned die; ten MCU / SoC packages with floating brand logos connected to glowing 3D energy cores shaped to each logo, locked 36 degrees apart; four vendors and fourteen technology capsules, all sharing a slow forward tilt with a larger foreground, distant rear, upright MCU labels and plane-aligned functional cards',content)
 md.write_text(content,encoding='utf-8')
 print(f'Built {path}: {path.stat().st_size:,} bytes; 10 equally spaced MCU nodes, {MCU_PERIOD}s shared lane; README hash {digest}')


if __name__=='__main__':build()
