# coding: utf-8
"""Render the shared daily report snapshot into a PDF and reusable social materials."""
import json, sys, zipfile
from urllib.parse import quote
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from xml.sax.saxutils import escape
from PIL import Image, ImageDraw, ImageFont, ImageOps
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor

ROOT=Path(__file__).resolve().parents[1]
DATE=sys.argv[1]
R=json.loads((ROOT/'data'/'reports'/(DATE+'.json')).read_text())
OUT=ROOT/'outputs'/'daily'/DATE
OUT.mkdir(parents=True,exist_ok=True)
FONT='/System/Library/Fonts/Supplemental/Arial Unicode.ttf'
HEAD='/System/Library/Fonts/STHeiti Medium.ttc'
if not Path(FONT).exists():
    raise RuntimeError('A Chinese-capable font is required; resolve a local font before rendering.')
pdfmetrics.registerFont(TTFont('AtlasCJK',FONT))
WINE='#592A42'; INK='#272B2A'; MUTED='#6D7767'; LINE='#DFE4D9'; GOLD='#AD854B'; PAPER='#F5F7F2'

def clean(s):
    return str(s).replace('\u2011','-').replace('\u2013','-').replace('\u2014','-')

# Data-driven report. Paragraphs split across pages; section starts keep the
# editorial rhythm without imposing a page count or limiting winery coverage.
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Flowable, Image as PDFImage, KeepTogether, Table, TableStyle,
)
from reportlab.lib.pagesizes import A4

PDF=OUT/('风土日报-'+DATE+'.pdf')
PAGE_W,PAGE_H=A4
MARGIN=42
CONTENT_W=PAGE_W-2*MARGIN
styles={}
for name,size,leading,color in [
    ('title',24,34,INK),('body',10.5,18,INK),
    ('small',8.5,14,MUTED),('heading',14,21,WINE),
    ('wine',12,19,WINE),('source',10,16,INK),
]:
    styles[name]=ParagraphStyle(
        name,fontName='AtlasCJK',fontSize=size,leading=leading,
        textColor=HexColor(color),wordWrap='CJK',spaceAfter=0,
        allowWidows=0,allowOrphans=0,
        keepWithNext=name in ('title','heading','wine','source'),
    )

def paragraph(value,style='body',link=None):
    markup=escape(clean(value)).replace('\n','<br/>')
    if link:
        markup='<a href="'+escape(str(link),{'"':'&quot;'})+'" color="'+WINE+'">'+markup+'</a>'
    return Paragraph(markup,styles[style])

def add(value,style='body',space=10,link=None):
    if value is None or str(value).strip()=='':return
    story.append(paragraph(value,style,link))
    if space:
        gap=Spacer(1,space)
        gap.keepWithNext=bool(styles[style].keepWithNext)
        story.append(gap)

def heading(value):
    add(value,'heading',9)

def section(value):
    while story and isinstance(story[-1],Spacer):story.pop()
    if story:story.append(PageBreak())
    add(value,'title',17)

def known(value,suffix=''):
    return '待确认' if value is None else str(value)+suffix

def refs(record):
    values=record.get('sourceIds',record.get('refs',[]))
    if isinstance(values,str):return values
    return ', '.join(str(value) for value in values)

def photo_blocks(media,width=CONTENT_W,max_height=235):
    path=OUT/'排版插图'/media['fileName']
    if not path.exists():
        raise RuntimeError('Run prepare-report-media.py first; missing '+str(path))
    with Image.open(path) as source:
        scale=min(width/source.width,max_height/source.height)
        photo=PDFImage(str(path),width=source.width*scale,height=source.height*scale)
    photo.hAlign='CENTER'
    return [photo,Spacer(1,7),paragraph('['+media['id']+'] '+media['caption'],'small'),
            paragraph(media['author']+' · '+media['license'],'small',media['sourceURL']),Spacer(1,12)]

def photos(anchor):
    for media in R.get('media',[]):
        if media.get('anchor')==anchor:
            story.append(KeepTogether(photo_blocks(media)))

def photo_pair(anchors):
    selected=[m for m in R.get('media',[]) if m.get('anchor') in anchors]
    if len(selected)==2:
        cells=[photo_blocks(m,(CONTENT_W-18)/2,200) for m in selected]
        pair=Table([[cells[0],cells[1]]],colWidths=[CONTENT_W/2]*2)
        pair.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),8)]))
        story.append(pair);story.append(Spacer(1,12))
    else:
        for anchor in anchors:photos(anchor)

class SummaryStats(Flowable):
    """One small fixed-height band; the document moves it intact if needed."""
    def __init__(self,items):
        Flowable.__init__(self)
        self.items=items;self.width=CONTENT_W;self.height=77
    def draw(self):
        gap=9;cell=(self.width-gap*(len(self.items)-1))/len(self.items)
        for i,(number,label) in enumerate(self.items):
            x=i*(cell+gap);self.canv.setFillColor(HexColor(PAPER))
            self.canv.roundRect(x,0,cell,self.height,6,fill=1,stroke=0)
            number=str(number);size=28
            while size>14 and pdfmetrics.stringWidth(number,'AtlasCJK',size)>cell-28:size-=1
            self.canv.setFont('AtlasCJK',size);self.canv.setFillColor(HexColor(WINE))
            self.canv.drawString(x+14,42,number)
            self.canv.setFont('AtlasCJK',9);self.canv.setFillColor(HexColor(MUTED))
            self.canv.drawString(x+14,17,label)

def page_decoration(c,doc):
    c.saveState()
    c.setFillColor(HexColor(WINE));c.rect(MARGIN,789,30,3,fill=1,stroke=0)
    c.setFont('AtlasCJK',9);c.drawString(82,787,'风土图鉴 / TERROIR ATLAS')
    c.setFillColor(HexColor(MUTED))
    issue=str(R.get('issue','')).strip()
    c.drawRightString(PAGE_W-MARGIN,787,DATE+(' · '+issue if issue else ''))
    c.setStrokeColor(HexColor(LINE));c.line(MARGIN,42,PAGE_W-MARGIN,42)
    c.setFont('AtlasCJK',8)
    c.drawString(MARGIN,26,'每日一产区 · 来源与核对范围见报告正文')
    c.drawRightString(PAGE_W-MARGIN,26,'第 '+str(doc.page)+' 页')
    c.restoreState()

story=[]
region=R['region']
added=R.get('added',{})
section(R['title'])
add(R.get('summary',''),space=18)
photos('hero')
story.append(SummaryStats([
    (len(added.get('wineryIds',[])),'新增酒庄'),
    (len(added.get('wineIds',[])),'新增酒款'),
    (len(R.get('news',[])),'新闻 / 采收'),
    (len(R.get('activities',[])),'近期活动'),
]))
story.append(Spacer(1,24))
if R.get('media'):
    add('本期配图为有明确来源的资料照片。原尺寸大图、排版插图及可复制图注随素材包交付。','small',0)
    story.append(Spacer(1,16))
    heading('本期仍待补充')
    for gap in region.get('gaps',[]):add('• '+gap,'small',4)
    section('本期收录与风土资料')
heading('本期收录范围')
add(region['name'],'small',8)
add(region.get('scope',''))
status_labels={
    'directory_checked':'本期官方名录核对完成',
    'partial':'本期核对尚未完成',
    'open_ended':'尚无权威名录分母',
}
add('覆盖状态：'+status_labels.get(region.get('status'),'待确认'))
producer_total=region.get('producerBaseline')
wine_total=region.get('winesListed')
producer_progress=(known(region.get('producersChecked'))+'/'+str(producer_total)+' 已核对'
                   if producer_total is not None else known(region.get('producersChecked'),'家已核对')+'；名录总数待确认')
wine_progress=(known(region.get('winesRecorded'))+'/'+str(wine_total)+' 已核对'
               if wine_total is not None else known(region.get('winesRecorded'),'款已核对')+'；公开目录总数待确认')
add('酒庄：'+producer_progress+'\n官网公开酒款：'+wine_progress+'\n'
    '目标产区酒款：'+known(region.get('targetAppellationWines'),'款')+
    '  ·  酒庄其他产区酒款：'+known(region.get('otherAppellationWines'),'款')+'\n'
    '本期已核实具体年份：'+known(region.get('verifiedVintages'),'条'),space=18)
heading('完成口径')
add(region.get('completionNote','本期核对范围以已列明来源为准，不代表互联网全部信息。'))
add(R.get('countingNote',''),'small',16)
created=datetime.fromisoformat(R['createdAt'].replace('Z','+00:00'))
if created.tzinfo is None:
    raise ValueError('createdAt must include a timezone so the report can show Beijing time.')
local_time=created.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M')
add('采编时间：'+local_time+'（北京时间）','small',0)
story.append(Spacer(1,12))
photo_pair(['grape',region.get('featuredWineryId','')])

section('产区酒庄与公开酒款')
add(region.get('introduction',''),space=18)
for winery_index,winery in enumerate(R.get('wineries',[]),1):
    heading(str(winery_index)+'. '+winery['name'])
    add(winery.get('summary',''),space=14)
    if winery['id']!=region.get('featuredWineryId'):photos(winery['id'])
    for wine_index,wine in enumerate(winery.get('wines',[]),1):
        add(str(winery_index)+'.'+str(wine_index)+'  '+wine['name'],'wine',5)
        add(wine.get('appellation','产区归属待核实'),'small',7)
        add(wine.get('summary',''))
        photos(wine['id'])
        if refs(wine):add('资料依据：'+refs(wine),'small')
    if not winery.get('wines'):
        add('本期尚无可列出的已核实酒款，具体缺口以本期核对说明为准。','small')
    if refs(winery):add('酒庄资料依据：'+refs(winery),'small')
    story.append(Spacer(1,12))
if not R.get('wineries'):
    add('本期报告未列出酒庄明细；覆盖进度与待补项目见收录范围。')
if not R.get('media'):
    heading('仍待补充')
    gaps=region.get('gaps',[])
    for gap in gaps:add('• '+gap,'small',6)
    if not gaps:add('本期未列出额外缺口；覆盖结论仍限于已说明的资料范围。','small')
    add('原始资料与逐条核对日期见“来源与下一步”；新收录不代表新成立或新上市。','small',0)

section('葡萄酒新闻与近期活动')
news=R.get('news',[])
if not news:add('本期未发现可核实的新增新闻。','small',18)
for item in news:
    heading(item['title'])
    add(item.get('summary',''))
    photos(item.get('id'))
    dates='发生/数据日期：'+known(item.get('occurrenceDate'))+'\n报道发布日期：'+known(item.get('publishedDate'))
    if item.get('freshness'):dates+=' · '+item['freshness']
    add(dates,'small')
    add(item.get('sourceName','原始来源')+' ↗','small',24,item.get('sourceURL'))
activities=R.get('activities',[])
if R.get('media') and activities:section('近期活动与场馆')
if not activities:add('本期未收录可核实的近期活动。','small',18)
for activity in activities:
    heading(activity['title'])
    add('活动日期：'+known(activity.get('dates'))+'\n地点：'+known(activity.get('location')),'small')
    add(activity.get('summary',''))
    photos(activity.get('id'))
    add(activity.get('sourceName','原始来源')+' · 查看主办方安排 ↗','small',24,activity.get('sourceURL'))
add('时间与位置说明：报道发布日期不等于实际发生日期。统计的截止日期、暂定性质与活动安排以各条原始资料为准；未核实的位置不作为精确地图点。','small',0)

section('来源与下一步')
add('以下为本期原始资料。点击来源标题可打开原文；每条保留各自的实际核对日期。','small',15)
for source in R.get('sources',[]):
    add('['+source['id']+'] '+source['label'],'source',4,source.get('url'))
    note=(source.get('note','')+' · ') if source.get('note') else ''
    add(note+'核对：'+known(source.get('checkedDate')),'small',9)
heading('下一步')
add(R.get('nextStep','下一期优先处理未完成的核对项目。'))
add('完整链接同时保存在公众号长文、小红书正文与本期资料清单中。生成的素材供自主发布，未自动发往任何第三方账号。','small',0)
if R.get('media'):
    section('配图来源与使用说明')
    add('原尺寸图片按来源保存；排版插图仅等比缩小并按相机方向显示，没有裁切。照片许可适用于照片；宣传页新增排版亦按对应照片的 CC BY-SA 许可提供。发布时保留以下署名、来源及许可链接。','small',16)
    for media in R['media']:
        add('['+media['id']+'] '+media['title'],'heading',4)
        add(media['caption'],'small',3)
        add(media['author']+' · '+media['license']+' · 原图 '+str(media['width'])+' × '+str(media['height']),'small',3)
        add('图片来源 ↗','small',2,media['sourceURL'])
        add(media['licenseURL'],'small',7,media['licenseURL'])
doc=SimpleDocTemplate(
    str(PDF),pagesize=A4,leftMargin=MARGIN,rightMargin=MARGIN,
    topMargin=91,bottomMargin=62,title='风土日报 '+DATE+' | '+region['name'],
    author='风土图鉴 · Terroir Atlas',allowSplitting=1,
)
doc.build(story,onFirstPage=page_decoration,onLaterPages=page_decoration)

# Six original text/data image cards, no scraped photos or unlicensed labels.
IW,IH=1080,1440
# Cards must never abort the whole daily bundle: the renderer retries at a
# smaller type scale instead of raising on a long block.
FIT_SCALE=1.0
def font(size,head=False):return ImageFont.truetype(HEAD if head and Path(HEAD).exists() else FONT,max(12,int(round(size*FIT_SCALE))))
def wrap(draw,text,f,width):
    lines=[]
    for para in clean(text).split('\n'):
        line=''
        for ch in para:
            if line and draw.textlength(line+ch,font=f)>width:lines.append(line);line=ch
            else:line+=ch
        lines.append(line)
    return lines
def text(draw,content,x,y,size=36,width=900,color=INK,head=False,leading=1.55,maxy=1290):
    f=font(size,head);lines=wrap(draw,content,f,width)
    for line in lines:
        if y+size>maxy:raise RuntimeError('Image overflow: '+content[:40])
        draw.text((x,y),line,font=f,fill=color);y+=int(size*leading)
    return y

def render_card(card,idx,scale):
    global FIT_SCALE
    FIT_SCALE=scale
    dark=idx==1;bg=WINE if dark else '#FFFFFF';fg='#FFFFFF' if dark else INK;muted='#D5C0CE' if dark else MUTED
    im=Image.new('RGB',(IW,IH),bg);d=ImageDraw.Draw(im)
    d.rectangle((76,70,125,77),fill=GOLD)
    text(d,'风土图鉴 / TERROIR ATLAS',147,61,25,width=800,color=muted)
    text(d,card['kicker'],76,142,24,width=920,color=muted)
    y=text(d,card['title'],76,187,76 if idx==1 else 62,width=930,color=fg,head=True,leading=1.35)
    y=text(d,card['subtitle'],76,y+25,32,width=930,color=muted)+44
    if card.get('stats'):
        for k,(n,label) in enumerate(card['stats']):
            x=76+(k%2)*480;sy=y+(k//2)*188
            d.rounded_rectangle((x,sy,x+443,sy+158),radius=14,fill='#6C3A53')
            text(d,n,x+28,sy+13,66,color='#FFFFFF',head=True)
            text(d,label,x+125,sy+67,28,width=280,color='#E9DDE4')
        y+=418
    for b in card['blocks']:
        d.line((76,y,1004,y),fill='#83546E' if dark else LINE,width=2);y+=int(27*max(scale,0.85))
        title_size=40 if idx==3 else 44
        y=text(d,b['title'],76,y,title_size,width=923,color=fg,head=True,leading=1.4)+12
        y=text(d,b['text'],76,y,40,width=923,color='#E1D2DC' if dark else MUTED,leading=1.45)+10
        y=text(d,'来源 '+b['refs'],76,y,23,width=923,color='#C5A5BA' if dark else '#98A18D')+26
    d.line((76,1330,1004,1330),fill='#83546E' if dark else LINE,width=2)
    text(d,DATE+' · 新收录不等于新上市',76,1352,22,width=800,color=muted,maxy=1430)
    d.text((948,1352),str(idx).zfill(2),font=font(25),fill=muted)
    return im

for idx,card in enumerate(R['cards'],1):
    im=None;last=None
    for scale in (1.0,0.94,0.88,0.82,0.76,0.70,0.64):
        try:
            im=render_card(card,idx,scale);break
        except RuntimeError as err:
            last=err;im=None
    if im is None:
        raise RuntimeError('Card %s does not fit at the smallest type scale: %s' % (idx,last))
    im.save(OUT/('图文-'+str(idx).zfill(2)+'.png'),optimize=True)
FIT_SCALE=1.0

photo_pages=OUT/'配图宣传页'
if R.get('media'):photo_pages.mkdir(exist_ok=True)
for media in R.get('media',[]):
    im=Image.new('RGB',(1080,1440),'#FFFFFF');d=ImageDraw.Draw(im)
    d.rectangle((76,65,125,72),fill=GOLD)
    text(d,'风土图鉴 / TERROIR ATLAS',147,57,25,color=MUTED)
    text(d,media['title'],76,130,58,head=True,leading=1.25,maxy=280)
    text(d,'资料照片 · '+media['capturedDate']+' · '+media['id'],76,271,27,color=MUTED)
    picture=Image.open(OUT/'排版插图'/media['fileName']).convert('RGB')
    picture.thumbnail((928,720),Image.Resampling.LANCZOS)
    d.rectangle((76,329,1004,1049),fill='#F5F3F4')
    im.paste(picture,(76+(928-picture.width)//2,329+(720-picture.height)//2))
    text(d,media['caption'],76,1072,34,width=928,color=INK,leading=1.4,maxy=1242)
    text(d,'摄影 / '+media['author'],76,1252,23,width=928,color=MUTED,leading=1.4,maxy=1322)
    text(d,media['license']+' · 完整照片与新增排版按此许可提供',76,1310,22,width=928,color=MUTED,maxy=1360)
    text(d,media['licenseURL'],76,1351,20,width=928,color=MUTED,maxy=1390)
    text(d,'来源：Wikimedia Commons · 原始链接见随附图注清单',76,1388,18,width=928,color=MUTED,maxy=1430)
    im.save(photo_pages/(media['id']+'-配图页.png'),optimize=True)

photo_credits=[]
for m in R.get('media',[]):
    photo_credits.append('['+m['id']+'] '+m['caption']+'\n摄影：'+m['author']+' / Wikimedia Commons\n许可：'+m['license']+' '+m['licenseURL']+'\n来源：'+m['sourceURL']+'\n'+m['changes'])
credits_text='\n\n'.join(photo_credits)
for key,label in [('xhs','小红书发布文案'),('wechat','公众号长文')]:
    s=R['social'][key]
    content='# '+s['title']+'\n\n'+'\n\n'.join(s['paragraphs'])+'\n\n'+' '.join(s.get('tags',[]))+'\n\n## 来源\n\n'+'\n\n'.join('['+x['id']+'] ['+x['label']+']('+x['url']+')' for x in R['sources'])
    if photo_credits:content+='\n\n## 配图图注与署名\n\n'+credits_text
    (OUT/(label+'.md')).write_text(content,encoding='utf-8')
if R.get('media'):
    (OUT/'图注与署名-可复制.txt').write_text(credits_text,encoding='utf-8')
    intro='原尺寸图片/：下载来源文件，保留原始像素和相机信息。\n排版插图/：长边最多2000像素，按相机方向等比缩小，未裁切、未放大。\n配图宣传页/：1080×1440竖版照片排版，图注与署名已置入。\n图文-01至06：原有信息图。\n公众号配图稿.html：双击打开，图片按正文顺序穿插；发公众号时上传对应图片。\n\n发布照片时一起使用图注与署名。CC BY-SA照片的修改部分以及本包新增配图页排版按对应照片许可提供；不改变其他独立正文的许可。资料照片不表示2026年事件现场或新上市酒款。\n\n'
    index='\n\n'.join('['+m['id']+'] '+m['title']+'\n插入位置：'+m['placement']+'\n原图：原尺寸图片/'+m['fileName']+' ('+str(m['width'])+'×'+str(m['height'])+')\n插图：排版插图/'+m['fileName']+'\n宣传页：配图宣传页/'+m['id']+'-配图页.png' for m in R['media'])
    (OUT/'图片使用与对应位置.txt').write_text(intro+index,encoding='utf-8')
    parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(R['title'])+'</title><style>body{max-width:780px;margin:48px auto;padding:0 22px;font:18px/1.95 system-ui;color:#292629}h1{font-size:32px;color:#592a42}figure{margin:32px 0}img{max-width:100%;max-height:620px;display:block;margin:auto;object-fit:contain}figcaption{font-size:14px;color:#646464;line-height:1.7;margin-top:12px}a{color:#592a42;overflow-wrap:anywhere}.photo-box{padding:16px;background:#f6f5f5}footer{font-size:14px;border-top:1px solid #ddd}</style><body><h1>'+escape(R['social']['wechat']['title'])+'</h1>']
    for n,para in enumerate(R['social']['wechat']['paragraphs']):
        parts.append('<p>'+escape(para).replace('\n','<br>')+'</p>')
        for m in R['media']:
            if m.get('wechatAfterParagraph')==n:
                parts.append('<figure><div class="photo-box"><img src="'+quote('排版插图/'+m['fileName'])+'" alt="'+escape(m['caption'],{'"':'&quot;'})+'"></div><figcaption>['+m['id']+'] '+escape(m['caption'])+'<br>'+escape(m['author'])+' / <a href="'+escape(m['sourceURL'])+'">Wikimedia Commons</a> · <a href="'+escape(m['licenseURL'])+'">'+m['license']+'</a><br><a href="'+quote('原尺寸图片/'+m['fileName'])+'">打开原尺寸图片</a></figcaption></figure>')
    parts.append('<footer><h2>原始资料</h2>'+''.join('<p>['+s['id']+'] <a href="'+escape(s['url'])+'">'+escape(s['label'])+'</a></p>' for s in R['sources'])+'<p>图片按相机方向显示并等比缩小；图注与署名随素材包提供。</p></footer></body></html>')
    (OUT/'公众号配图稿.html').write_text('\n'.join(parts),encoding='utf-8')
(OUT/'本期资料清单.json').write_text(json.dumps(R,ensure_ascii=False,indent=2),encoding='utf-8')
bundle_files=[PDF,OUT/'小红书发布文案.md',OUT/'公众号长文.md',OUT/'本期资料清单.json']
bundle_files += [OUT/('图文-'+str(i).zfill(2)+'.png') for i in range(1,len(R['cards'])+1)]
if R.get('media'):
    bundle_files += [OUT/name for name in ['图注与署名-可复制.txt','图片使用与对应位置.txt','图片清单.json','公众号配图稿.html']]
    for m in R['media']:
        bundle_files += [OUT/'原尺寸图片'/m['fileName'],OUT/'排版插图'/m['fileName'],photo_pages/(m['id']+'-配图页.png')]
with zipfile.ZipFile(OUT/('风土日报-'+DATE+'-发布素材包.zip'),'w',zipfile.ZIP_DEFLATED) as z:
    for f in bundle_files:z.write(f,f.relative_to(OUT))
if R.get('media'):
    with zipfile.ZipFile(OUT/('风土日报-'+DATE+'-原尺寸配图库.zip'),'w',zipfile.ZIP_DEFLATED) as z:
        for m in R['media']:z.write(OUT/'原尺寸图片'/m['fileName'],'原尺寸图片/'+m['fileName'])
        for name in ['图注与署名-可复制.txt','图片使用与对应位置.txt','图片清单.json']:z.write(OUT/name,name)
print('Created report,',len(R['cards']),'image cards and publishing copy in',OUT)
