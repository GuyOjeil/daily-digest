"""Deterministic, auditable 24-hour prioritization and digest construction."""
import datetime as dt
import hashlib
import re
from collections import Counter, defaultdict

CATEGORIES = ['Top stories','Lebanon and Middle East','Power Systems','Renewable Energy','Energy Storage','Control and Automation','Power Electronics','Electronics','Semiconductors','Research','Tools','Tech News']
REGION = ['lebanon','lebanese','beirut','edl','electricite du liban','électricité du liban','middle east','mena','gulf','saudi','uae','dubai','abu dhabi','egypt','jordan','iraq','syria','oman','qatar','kuwait','morocco']
LEBANON = ['lebanon','lebanese','beirut','edl','electricite du liban','électricité du liban']
INTERESTS = {
 'Power Systems': ['power system','power grid','electric grid','grid','transmission line','transmission','distribution network','substation','transformer','protection relay','relay','blackout','outage','utility','utilities','load flow','power flow','frequency regulation','voltage control','smart grid','microgrid','smart meter','hvdc','switchgear','circuit breaker','electricity demand','electricity market','megawatt','gigawatt','interconnection'],
 'Renewable Energy': ['solar','photovoltaic','pv','wind turbine','wind farm','offshore wind','renewable','hydropower','geothermal','green hydrogen','electrolyzer','clean energy','net zero','decarbon','biomass','solar panel','perovskite'],
 'Energy Storage': ['battery','batteries','energy storage','bess','lithium','solid-state battery','sodium-ion','flow battery','pumped hydro','grid storage','ev charging','ev charger','charging station','lfp','lithium iron phosphate','battery pack','battery cell'],
 'Control and Automation': ['control system','model predictive','mpc','state estimation','grid stability','power system stability','plc','scada','industrial automation','automation system','servo','motor control','feedback control','kalman filter','robust control','pid controller','control engineering'],
 'Power Electronics': ['inverter','converter','power electronics','gan','sic','silicon carbide','gallium nitride','mosfet','igbt','rectifier','dc-dc','motor drive','wireless power','power supply','switching converter'],
 'Electronics': ['circuit','analog','amplifier','sensor','pcb','capacitor','inductor','oscilloscope','signal processing','fpga','antenna','rf','voltage'],
 'Semiconductors': ['semiconductor','chip','foundry','wafer','transistor','lithography','packaging','tsmc','dram'],
 'Research': ['researchers','new study','prototype','breakthrough','university','experiment','laboratory']
}
IMPACT = {
 'critical': ['blackout','grid failure','major outage','recall','fire at','emergency','cyberattack on grid'],
 'high': ['record','breakthrough','launch','announces','unveils','new standard','efficiency','commissioned','investment','approved','largest','milestone','regulation','tariff'],
 'medium':['research','prototype','design','study','test','review','guide','project','pilot']
}
BROAD_SOURCES = ('electrek','cleantechnica','agbi','mercom','solarquarter','l\'orient')  # general clean-tech sites: keep only stories with electrical words
LOW_VALUE = ['submitted by /u/', 'weekly roundup', 'discussion thread', 'sponsored']
STOP = set('with from that this their where about using across into through which have more new paper study approach based results how why what for the and are to in of on by an as at'.split())


def hit(term, text):
    """True when the whole word or phrase appears in the text (plural allowed)."""
    return re.search(r'(?<![a-z0-9])'+re.escape(term)+r'(?:s|es)?(?![a-z0-9])', text) is not None

def electrical_hits(row):
    text=(row.get('title','')+' '+row.get('summary','')[:400]).lower()
    return {t for terms in INTERESTS.values() for t in terms if hit(t,text)}

def tokens(title):
    return {t for t in re.findall(r'[a-z0-9]{3,}',title.lower()) if t not in STOP}

def classify(row):
    cat=row.get('category','Tech News')
    title=(row.get('title','')+' '+row.get('summary','')[:240]).lower()
    if any(hit(w,title) for w in REGION) and electrical_hits(row): return 'Lebanon and Middle East'
    # Mixed sources are sorted into a specific electrical topic when the words clearly match.
    if cat in ('Tech News','Research','Tools'):
        best,bestn=None,0
        for label in ('Power Systems','Renewable Energy','Energy Storage','Control and Automation','Power Electronics','Electronics','Semiconductors'):
            hits=sum(hit(w,title) for w in INTERESTS[label])
            if hits>bestn: best,bestn=label,hits
        if best: return best
    return cat if cat in CATEGORIES else 'Tech News'

def score(row):
    title=row['title'].lower(); body=(title+' '+row.get('summary','')[:400].lower())
    category=classify(row)
    relevant=sum(min(2, sum(1 for word in terms if hit(word,body))) for key,terms in INTERESTS.items())
    matched=[k for k,terms in INTERESTS.items() if any(hit(term,body) for term in terms)]
    source=row.get('source','').lower()
    trust=3 if any(v in source for v in ('ieee','eetimes','ee times','utility dive','power engineering','t&d world','semiconductor engineering')) else 1 if any(v in source for v in ('arxiv','reddit')) else 2
    importance=5 if any(k in body for k in IMPACT['critical']) else 3 if any(k in title for k in IMPACT['high']) else 2 if any(k in body for k in IMPACT['medium']) else 1
    penalty=3 if any(k in body for k in LOW_VALUE) else 0
    region_boost=(5 if any(hit(w,body) for w in LEBANON) else 2 if any(hit(w,body) for w in REGION) else 0) if matched else 0
    if category=='Research' and 'arxiv' in source: penalty+=2
    value=max(0, round(importance*2+min(relevant,6)+trust+region_boost-penalty))
    label='High signal' if value>=14 else 'Worth watching' if value>=10 else 'Other developments'
    return value,label,matched

def within_window(item, now, hours=24):
    try:
        date=dt.datetime.fromisoformat(str(item['published']).replace('Z','+00:00'))
        if date.tzinfo is None: return False
        return now-dt.timedelta(hours=hours)<=date.astimezone(dt.timezone.utc)<=now
    except (TypeError, ValueError): return False

def group_events(rows, now, hours=24):
    """Group near-identical titles but keep different technical contributions separate."""
    seen=[]
    for row in rows:
        if not within_window(row,now,hours): continue
        r=dict(row); r['category']=classify(r)
        r['score'],r['priority'],r['interests']=score(r)
        if (row.get('category') in ('Tech News','Research','Tools') or any(b in row.get('source','').lower() for b in BROAD_SOURCES)) and len(electrical_hits(r))<2: continue  # not electrical engineering
        ts=tokens(r['title']); r['event_id']=hashlib.sha256(r['url'].encode()).hexdigest()[:12]
        match=None
        for entry in seen:
            other=tokens(entry['title'])
            sim=len(ts&other)/max(1,len(ts|other))
            if sim>=0.70 and len(ts&other)>=min(3,len(ts),len(other)):
                match=entry;break
        if match is not None:
            match.setdefault('coverage',[]).append({'source':r['source'],'url':r['url']})
            if r['score']>match['score']:
                # Keep canonical event id and merged coverage; prefer higher quality evidence.
                old={'source':match['source'],'url':match['url']}
                history=match['coverage'];ident=match['event_id']
                match.update(r);match['coverage']=history+[old];match['event_id']=ident
        else:
            r['coverage']=[];seen.append(r)
    seen.sort(key=lambda x:(x['score'],x['published']),reverse=True)
    return seen

def build_report(events, fetched, inserted, now, health=None, narratives=None, hours=24):
    groups=defaultdict(list)
    for item in events: groups[item['category']].append(item)
    limit=int(__import__('os').getenv('TOP_STORIES','10'))
    top=[];papers=0
    for e in events:
        if len(top)>=limit: break
        if 'arxiv' in e.get('source','').lower():
            if papers>=2: continue  # keep research papers to 2 in the top list
            papers+=1
        top.append(e)
    cats=[]
    for category in CATEGORIES[1:]:
        items=groups.get(category,[])
        if not items: continue
        high=sum(x['priority']=='High signal' for x in items)
        cats.append({'name':category,'count':len(items),'high':high,'top':items[:3],'items':items,
            'narrative':(narratives or {}).get(category) or evidence_summary(category,items)})
    health=health or []
    failed=sum(x.get('status')!='ok' for x in health)
    return {'generated':now.isoformat(),'window_hours':hours,'window_start':(now-dt.timedelta(hours=hours)).isoformat(),
      'stats':{'events':len(events),'high':sum(x['priority']=='High signal' for x in events),
        'sources_reporting':len({x['source'] for x in events}), 'categories':len(cats), 'records_inserted':inserted,
        'fetched':fetched,'sources_failed':failed,'source_checks':len(health)},
      'top':top,'categories':cats,'health':health,
      'executive':(narratives or {}).get('executive') or executive_summary(top,hours)}

def evidence_summary(category,items):
    if not items: return 'No verified published findings during this window.'
    titles='; '.join(x['title'] for x in items[:3])
    return f"{len(items)} distinct {category.lower()} developments appeared in this time window. Highest-ranked topics: {titles}. These are relevance signals, not independently verified breakthroughs; consult the linked sources for evidence and actual performance."

def executive_summary(top,hours=24):
    if not top:return 'No dated findings were collected for the last '+str(hours)+' hours. This may also indicate source failures; see Source health.'
    count=Counter(x['category'] for x in top)
    focus=', '.join(f'{cat} ({n})' for cat,n in count.most_common(4))
    return f'The highest-ranked developments in the last {hours} hours concentrate on {focus}. Scores reflect relevance, source type and headline signals, not independently established impact. Read the linked evidence before making decisions.'
