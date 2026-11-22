"""Deterministic, auditable 24-hour prioritization and digest construction."""
import datetime as dt
import hashlib
import re
from collections import Counter, defaultdict

CATEGORIES = ['Top stories','Power and Energy','Electronics','Embedded','Semiconductors','Tech News','Research','Security','Open source','Regional']
INTERESTS = {
 'Power and Energy': ['power grid','grid','solar','wind','battery','batteries','energy storage','inverter','transformer','substation','electric vehicle','ev charging','charger','nuclear','renewable','electricity','megawatt','gigawatt','hydrogen','smart meter','microgrid'],
 'Electronics': ['circuit','pcb','analog','oscilloscope','sensor','amplifier','power supply','voltage','current','capacitor','resistor','led','display','kicad','soldering','fpga','signal'],
 'Embedded': ['esp32','arduino','raspberry pi','pico','microcontroller','stm32','firmware','rtos','iot','risc-v','micropython','circuitpython','zephyr','bluetooth','wifi','lora','matter'],
 'Semiconductors': ['chip','semiconductor','foundry','tsmc','wafer','transistor','nanometer','gpu','memory','dram','gan','sic','silicon carbide','lithography','packaging'],
 'Security': ['vulnerability','exploit','attack','security','malware','ransomware','zero-day','firmware update','privacy','data leak'],
 'Regional': ['lebanon','beirut','arabic','middle east','mena','gulf','saudi','uae'],
 'Research': ['researchers','new study','prototype','breakthrough','paper','university','experiment'],
 'Open source': ['open source','open-source','github','release','sdk','library','toolchain']
}
IMPACT = {
 'critical': ['actively exploited','remote code execution','zero-day','emergency patch','major vulnerability','recall','blackout'],
 'high': ['released','launch','release','breakthrough','record','new chip','announces','unveils','standard','efficiency','cost reduction','shortage','ban','investment'],
 'medium':['research','prototype','design','test','review','guide','how to','project']
}
LOW_VALUE = ['submitted by /u/', 'weekly roundup', 'discussion thread', 'sponsored']
STOP = set('with from that this their where about using across into through which have more new paper study approach based results how why what for the and are to in of on by an as at'.split())

def tokens(title):
    return {t for t in re.findall(r'[a-z0-9]{3,}',title.lower()) if t not in STOP}

def classify(row):
    cat=row.get('category','Tech News')
    title=(row.get('title','')+' '+row.get('summary','')[:240]).lower()
    # Route general tech news into a specific topic when the words clearly match.
    if cat in ('Tech News','Research','Open source'):
        best,bestn=None,1
        for label in ('Power and Energy','Semiconductors','Embedded','Electronics','Security','Regional'):
            hits=sum(bool(re.search(r'\b'+re.escape(w)+r'\b',title)) for w in INTERESTS[label])
            if hits>bestn: best,bestn=label,hits
        if best: return best
    return cat if cat in CATEGORIES else 'Tech News'

def score(row):
    title=row['title'].lower(); body=(title+' '+row.get('summary','')[:400].lower())
    category=classify(row)
    relevant=sum(min(2, sum(1 for word in terms if word in body)) for key,terms in INTERESTS.items())
    matched=[k for k,terms in INTERESTS.items() if any(term in body for term in terms)]
    source=row.get('source','').lower()
    trust=3 if any(v in source for v in ('ieee','eetimes','ee times','semiconductor engineering','utility dive','cisa')) else 1 if any(v in source for v in ('arxiv','reddit')) else 2
    importance=5 if any(k in body for k in IMPACT['critical']) else 3 if any(k in title for k in IMPACT['high']) else 2 if any(k in body for k in IMPACT['medium']) else 1
    penalty=3 if any(k in body for k in LOW_VALUE) else 0
    if category=='Research' and 'arxiv' in source: penalty+=2
    value=max(0, round(importance*2+min(relevant,6)+trust-penalty))
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

def build_report(events, fetched, inserted, now, health=None, narratives=None):
    groups=defaultdict(list)
    for item in events: groups[item['category']].append(item)
    top=events[:int(__import__('os').getenv('TOP_STORIES','10'))]
    cats=[]
    for category in CATEGORIES[1:]:
        items=groups.get(category,[])
        if not items: continue
        high=sum(x['priority']=='High signal' for x in items)
        cats.append({'name':category,'count':len(items),'high':high,'top':items[:3],'items':items,
            'narrative':(narratives or {}).get(category) or evidence_summary(category,items)})
    health=health or []
    failed=sum(x.get('status')!='ok' for x in health)
    return {'generated':now.isoformat(),'window_hours':24,'window_start':(now-dt.timedelta(hours=24)).isoformat(),
      'stats':{'events':len(events),'high':sum(x['priority']=='High signal' for x in events),
        'sources_reporting':len({x['source'] for x in events}), 'categories':len(cats), 'records_inserted':inserted,
        'fetched':fetched,'sources_failed':failed,'source_checks':len(health)},
      'top':top,'categories':cats,'health':health,
      'executive':(narratives or {}).get('executive') or executive_summary(top)}

def evidence_summary(category,items):
    if not items: return 'No verified published findings during this window.'
    titles='; '.join(x['title'] for x in items[:3])
    return f"{len(items)} distinct {category.lower()} developments appeared in the last 24 hours. Highest-ranked topics: {titles}. These are relevance signals, not independently verified breakthroughs; consult the linked sources for evidence and actual performance."

def executive_summary(top):
    if not top:return 'No dated findings were collected for the last 24 hours. This may also indicate source failures; see Source health.'
    count=Counter(x['category'] for x in top)
    focus=', '.join(f'{cat} ({n})' for cat,n in count.most_common(4))
    return f'The highest-ranked developments in this 24-hour window concentrate on {focus}. Scores reflect relevance, source type and headline signals, not independently established impact. Read the linked evidence before making decisions.'
