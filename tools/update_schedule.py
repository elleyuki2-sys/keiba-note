import json,re,sys,time
from datetime import date,timedelta
from urllib.request import Request,urlopen
from html import unescape
from pathlib import Path
COURSES=r"札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉"
HEADING=re.compile(rf"^(\d+)回\s*({COURSES})\s*(\d+)日$")
def fetch(url,timeout=30):
 req=Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; KEIBA-NOTE/5.4.4)"})
 with urlopen(req,timeout=timeout) as r:return r.read().decode("utf-8","replace")
def norm(s):
 s=unescape(str(s)).replace("\xa0"," ").replace("\u3000"," ");s=re.sub(r"\*\*(.*?)\*\*",r"\1",s).replace("`","");return re.sub(r"\s+"," ",s).strip()
def parse_text(text,ds):
 lines=[norm(x) for x in str(text).splitlines() if norm(x)];out=[];course="";meeting=""
 for line in lines:
  clean=line.strip().strip("|").strip();h=HEADING.match(clean)
  if h:course=h.group(2);meeting=f"{h.group(1)}回{h.group(3)}日";continue
  m=re.match(r"^\|?\s*(\d+)レース\s*\|\s*(.*?)\s*\|\s*(\d+)時(\d+)分\s*\|?\s*$",line) or re.match(r"^(\d+)レース\s*\|\s*(.*?)\s*\|\s*(\d+)時(\d+)分\s*$",clean)
  if not m or not course:continue
  race=int(m.group(1));
  if not 1<=race<=12:continue
  cond=re.sub(r"\s+"," ",m.group(2)).strip();dm=re.search(r"([0-9,]+)\s*（(芝(?:・外)?|ダ|芝→ダート|ダート)）",cond)
  distance=(dm.group(1).replace(",","")+"m") if dm else "";surface=dm.group(2) if dm else "";surface="ダ" if surface=="ダート" else surface
  name=re.sub(r"\s+[0-9,]+\s*（.*","",cond).strip() or cond
  out.append({"date":ds,"course":course,"race":race,"raceName":name,"raceCondition":cond,"distance":distance,"surface":surface,"startTime":f"{int(m.group(3)):02d}:{int(m.group(4)):02d}","raceKey":f"{ds}-{course}-{race}","meeting":meeting})
 seen=set();return [r for r in out if not ((r["date"],r["course"],r["race"]) in seen or seen.add((r["date"],r["course"],r["race"]))) ]
def strip_html(html):
 html=re.sub(r'<script[\s\S]*?</script>',' ',html,flags=re.I);html=re.sub(r'<style[\s\S]*?</style>',' ',html,flags=re.I);html=re.sub(r'<br\s*/?>','\n',html,flags=re.I);html=re.sub(r'</(?:p|div|tr|li|h[1-6]|table)>','\n',html,flags=re.I);html=re.sub(r'<(?:td|th)\b[^>]*>','\n',html,flags=re.I);text=re.sub(r'<[^>]+>',' ',html);return '\n'.join(norm(x) for x in text.splitlines() if norm(x))
def fetch_date(ds):
 d=date.fromisoformat(ds);target=f"https://www.jra.go.jp/keiba/calendar{d.year}/{d.year}/{d.month}/{d.month:02d}{d.day:02d}.html"
 for url,jina in [(f"https://r.jina.ai/{target}",True),(target,False)]:
  try:
   raw=fetch(url);r=parse_text(raw,ds) if jina else parse_text(strip_html(raw),ds)
   if r:return r
  except Exception as e:print(f"WARN {ds}: {e}",file=sys.stderr)
 return []
def main():
 today=date.today();path=Path("data/jra-schedule.json")
 try:old=json.loads(path.read_text(encoding="utf-8"))
 except:old={"races":[]}
 existing={(r.get("date"),r.get("course"),int(r.get("race",0))):r for r in old.get("races",[]) if isinstance(r,dict)};fetched=0
 for i in range(-3,15):
  ds=(today+timedelta(days=i)).isoformat();races=fetch_date(ds)
  if races:
   fetched+=len(races)
   for r in races:existing[(r["date"],r["course"],r["race"])]=r
 if not fetched:raise SystemExit("ERROR: 0 JRA races fetched; existing JSON was not overwritten.")
 races=sorted(existing.values(),key=lambda r:(r.get("date",""),r.get("course",""),int(r.get("race",0))))
 payload={"updatedAt":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"source":"JRA official daily program via GitHub Actions/Jina Reader","dates":sorted({r["date"] for r in races}),"races":races};path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8");print(f"OK: fetched {fetched} races; stored {len(races)} races")
if __name__=="__main__":main()
