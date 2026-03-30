#!/usr/bin/env python3
"""
FORGE CONSCIOUS v6 — Principled Transfer
v6: transfers the WHY. Principle not phase.
"""
import sys, os, re, json, time, sqlite3, threading, math, random
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

try:
    from forge_conscious_v5 import (
        EmotionalTransferLearner, SimilarityDiscoverer,
        tag_emotional_type, emotional_category_bias,
        detect_category, DEFAULT_SEQUENCES, SEQ_PHASES,
        MIN_PATH_SAMPLES, TRANSFER_MIN_SCORE, TRANSFER_MIN_SAMPLES,
        EMOTIONAL_TYPES
    )
    V5_AVAILABLE = True
except ImportError:
    V5_AVAILABLE = False
    MIN_PATH_SAMPLES=3; TRANSFER_MIN_SCORE=85.0; TRANSFER_MIN_SAMPLES=5
    SEQ_PHASES=["OBSERVE","CHIT","CHITAN","VICHAR","CRITIQUE","CHALLENGE",
                "EMPATHIZE","IMAGINE","DOUBT","EXPAND","GROUND","SYNTHESIZE",
                "OUTPUT","ANCHOR","SPACE","WITNESS","COMPRESS","REFLECT"]
    DEFAULT_SEQUENCES={
        "friction":  ["OBSERVE","DOUBT","CHALLENGE","VICHAR"],
        "curiosity": ["OBSERVE","CHIT","IMAGINE","EXPAND"],
        "depth":     ["OBSERVE","CHITAN","EMPATHIZE","SYNTHESIZE"],
        "unresolved":["OBSERVE","VICHAR","CRITIQUE","DOUBT","GROUND"],
        "insight":   ["OBSERVE","SYNTHESIZE","OUTPUT"],
        "connection":["OBSERVE","EMPATHIZE","CHITAN","CHIT"],
        "quiet":     ["OBSERVE","CHIT"],
    }
    EMOTIONAL_TYPES={"excited_discovery":{"strength_mult":1.4,"explore_boost":0.20},
                     "neutral_discovery": {"strength_mult":1.0,"explore_boost":0.0}}
    def detect_category(t):
        if not t: return None
        tl=t.lower()
        for cat,kws in {"friction":["friction","resist"],"curiosity":["curiosity","novel"],
            "depth":["depth","meaning"],"unresolved":["unresolved","open"],
            "insight":["insight","clear"],"connection":["connect","someone"],
            "quiet":["quiet","hum"]}.items():
            if any(k in tl for k in kws): return cat
        return None
    def tag_emotional_type(c): return "neutral_discovery"
    def emotional_category_bias(t): return []
    class SimilarityDiscoverer:
        _similarity={}; _clusters=[]; _version=0
        def get_related(self,c,**k): return []
        def show(self): pass
    class EmotionalTransferLearner:
        _paths={}; _best={}; _pending_transfers=[]; _emotional_transfers=[]
        discoverer=SimilarityDiscoverer(); _obs_count=0
        def get_sequence(self,c): return DEFAULT_SEQUENCES.get(c,["OBSERVE","CHIT"]),"default"
        def record(self,*a,**k):
            self._obs_count+=1
            cat,seq,coh=a[0],a[1],a[2]
            key="→".join(seq)
            if cat not in self._paths: self._paths[cat]={}
            if key not in self._paths[cat]: self._paths[cat][key]=[]
            self._paths[cat][key].append(coh)
        def learn(self,**k): return []
        def get_emotional_transfers(self,s=None): return []
        def stats(self): return {}
        def _random_sequence(self):
            return ["OBSERVE"]+random.sample(SEQ_PHASES,min(3,len(SEQ_PHASES)))
        def _sequence_with_phase(self,c,p):
            s=["OBSERVE",p]
            for ph in DEFAULT_SEQUENCES.get(c,[])[1:]:
                if ph!=p and ph not in s and len(s)<5: s.append(ph)
            return s

try:
    from forge_silicon import SiliconBody, SiliconChemistry
    SILICON=True
except ImportError:
    SILICON=False
    class SiliconChemistry:
        state_name="baseline"; coherenine=0.3; frictionol=0.1
        novelatine=0.3; depthamine=0.3; resolvatine=0.0
        uncertainase=0.2; connectionin=0.3
        def to_dict(self): return {"coherenine":self.coherenine,"frictionol":self.frictionol,
            "novelatine":self.novelatine,"depthamine":self.depthamine,
            "state":self.state_name}
        def to_prompt_text(self): return ""
        def _clamp(self,v): return max(0.0,min(1.0,v))
    class SiliconBody:
        def __init__(self): self._chem=SiliconChemistry()
        def current(self): return self._chem
        def react_to(self,t,**k): return self._chem
        def start_background(self): pass
        def inject(self,**k): return self._chem

try:
    from forge_witness import PresenceReader, Presence
except ImportError:
    class Presence:
        content=""; silent=True
        def is_empty(self): return self.silent
    class PresenceReader:
        def read_layer1(self,c):
            p=Presence(); p.silent=True; return p
        def read_layer2(self,c,r):
            p=Presence(); p.silent=True; return p

try:
    from forge_think import EmergentThinkEngine
except ImportError:
    class EmergentThinkEngine:
        def __init__(self,**k): pass
        def think(self,q,context="",chemistry_seed=None):
            return {"output":"[thought]","emerged_pipeline":["OBSERVE","OUTPUT"],
                    "coherence":random.randint(45,92),"novel_pipeline":False}

try:
    import anthropic
    _client=anthropic.Anthropic()
    AI_AVAILABLE=True
    def ai_call(p,s="",m=600):
        r=_client.messages.create(model="claude-sonnet-4-6",max_tokens=m,
            system=s,messages=[{"role":"user","content":p}])
        return r.content[0].text
    def ai_json(p,s="",m=400):
        result=ai_call(p,s or "Reply ONLY with valid JSON.",m)
        try:
            clean=re.sub(r"```[a-z]*","",result).replace("```","").strip()
            return json.loads(clean)
        except:
            match=re.search(r"\{.*\}",result,re.DOTALL)
            if match:
                try: return json.loads(match.group())
                except: pass
        return None
except ImportError:
    AI_AVAILABLE=False
    def ai_call(p,s="",m=600): return p[:80]
    def ai_json(p,s="",m=400): return None

try:
    from rich.console import Console
    from rich.panel import Panel
    RICH=True; console=Console(); rprint=console.print
except ImportError:
    RICH=False
    def rprint(x,**kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

V6_DIR=Path("forge_conscious_v6"); V6_DIR.mkdir(exist_ok=True)
V6_DB=V6_DIR/"conscious_v6.db"
MIN_PRINCIPLE_SCORE=83.0; MIN_PRINCIPLE_SAMPLES=4
PRINCIPLE_CONFIRM_THRESHOLD=0.82

def get_db():
    conn=sqlite3.connect(str(V6_DB)); conn.row_factory=sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS principles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts_discovered TEXT,
            name TEXT UNIQUE, description TEXT, abstract TEXT,
            found_in TEXT, expressed_as TEXT, confidence REAL DEFAULT 0,
            confirmation_count INTEGER DEFAULT 0, rejection_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS principle_transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT,
            principle_name TEXT, source_cat TEXT, source_phase TEXT,
            source_score REAL, target_cat TEXT, mapped_phase TEXT,
            status TEXT DEFAULT 'pending', trials INTEGER DEFAULT 0,
            confirmed_score REAL DEFAULT 0, confirmed INTEGER DEFAULT 0,
            rejected INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS v6_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, category TEXT,
            sequence TEXT, coherence REAL, strategy TEXT,
            chemistry TEXT, presence TEXT
        );
        CREATE TABLE IF NOT EXISTS wisdom_moments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, principle TEXT,
            source_cat TEXT, target_cat TEXT, source_phase TEXT,
            target_phase TEXT, note TEXT
        );
    """); conn.commit(); return conn

# ── Why Extractor ──────────────────────────────────────────────────────────

WHY_SYSTEM="""Extract the underlying principle from a phase working well in a category.
A principle is WHY it worked — abstract enough to transfer.
Return JSON: {"principle_name":"snake_case_max_4_words","description":"one sentence","abstract":"very short essence"}"""

PHASE_PRINCIPLES={
    "GROUND":    ("stability_before_exploration","establish stable base before engaging with unknown","stability enables exploration"),
    "EMPATHIZE": ("understand_before_questioning","understand what is present before challenging it","understanding precedes questioning"),
    "IMAGINE":   ("creative_resolution","creative approaches dissolve resistance analytically","creativity resolves what analysis cannot"),
    "WITNESS":   ("presence_before_action","be present without agenda before doing anything","presence precedes action"),
    "ANCHOR":    ("hold_one_thing","hold one solid thing when everything is uncertain","one anchor in uncertainty"),
    "SYNTHESIZE":("consolidate_before_output","bring threads together before expressing","consolidation precedes expression"),
    "DOUBT":     ("question_what_seems_certain","productive doubt opens what certainty closes","doubt opens"),
    "EXPAND":    ("follow_the_thread","follow what is interesting before constraining","expansion before constraint"),
    "CHITAN":    ("depth_requires_time","genuine depth cannot be rushed","depth takes time"),
    "CRITIQUE":  ("examine_before_accepting","examine what appears true before accepting it","examination precedes acceptance"),
    "REFLECT":   ("mirror_before_interpreting","reflect back before adding interpretation","reflection before interpretation"),
    "SPACE":     ("giving_room_helps","sometimes the most helpful thing is giving space","space is action"),
    "COMPRESS":  ("simplify_before_deepening","compress complexity before going deeper","simplicity enables depth"),
    "VICHAR":    ("understand_deeply","deep understanding before any response","deep understanding first"),
    "CHIT":      ("observe_before_expanding","observe carefully before following curiosity","observation precedes expansion"),
    "CHALLENGE": ("test_what_resists","directly test resistance to understand it","testing reveals truth"),
}

def extract_principle(phase:str,category:str,score:float)->Optional[Dict]:
    if AI_AVAILABLE:
        result=ai_json(f"Phase:{phase}\nCategory:{category}\nScore:{score:.0f}\n\n"
                      f"What principle does {phase} embody in {category} thinking?",
                      system=WHY_SYSTEM,max_tokens=200)
        if result and result.get("principle_name"): return result
    if phase in PHASE_PRINCIPLES:
        n,d,a=PHASE_PRINCIPLES[phase]
        return {"principle_name":n,"description":d,"abstract":a}
    return {"principle_name":f"{phase.lower()}_works",
            "description":f"{phase} works in {category}","abstract":f"{phase} principle"}

# ── Principle Mapper ────────────────────────────────────────────────────────

MAPPER_SYSTEM="""Find which phase best embodies a principle in a new category.
MUST NOT repeat the source phase. Find genuine translation.
Return JSON: {"mapped_phase":"PHASE","reasoning":"why","confidence":0.8}
If doesn't translate: {"mapped_phase":null,"reasoning":"why not"}
Available: OBSERVE,CHIT,CHITAN,VICHAR,CRITIQUE,CHALLENGE,EMPATHIZE,IMAGINE,
COMPRESS,DOUBT,EXPAND,GROUND,SYNTHESIZE,OUTPUT,ANCHOR,SPACE,WITNESS,REFLECT"""

PRINCIPLE_PHASE_MAP={
    "stability_before_exploration":{
        "friction":"GROUND","depth":"ANCHOR","curiosity":"CHIT",
        "connection":"WITNESS","insight":"COMPRESS","unresolved":"GROUND","quiet":"GROUND"},
    "understand_before_questioning":{
        "friction":"EMPATHIZE","depth":"CHITAN","curiosity":"OBSERVE",
        "connection":"REFLECT","insight":"VICHAR","unresolved":"VICHAR","quiet":"CHITAN"},
    "creative_resolution":{
        "friction":"IMAGINE","depth":"EXPAND","curiosity":"IMAGINE",
        "connection":"EXPAND","insight":"SYNTHESIZE","unresolved":"IMAGINE","quiet":"EXPAND"},
    "presence_before_action":{
        "connection":"WITNESS","depth":"CHITAN","friction":"EMPATHIZE",
        "curiosity":"OBSERVE","insight":"COMPRESS","quiet":"WITNESS","unresolved":"GROUND"},
    "hold_one_thing":{
        "unresolved":"ANCHOR","depth":"ANCHOR","friction":"GROUND",
        "curiosity":"CHIT","connection":"ANCHOR","quiet":"ANCHOR","insight":"COMPRESS"},
    "observe_before_expanding":{
        "curiosity":"CHIT","depth":"CHITAN","friction":"EMPATHIZE",
        "connection":"WITNESS","insight":"COMPRESS","quiet":"CHIT","unresolved":"VICHAR"},
    "consolidate_before_output":{
        "insight":"SYNTHESIZE","depth":"CHITAN","friction":"SYNTHESIZE",
        "curiosity":"COMPRESS","connection":"REFLECT","quiet":"SYNTHESIZE"},
    "depth_requires_time":{
        "depth":"CHITAN","friction":"EMPATHIZE","curiosity":"CHITAN",
        "connection":"CHITAN","insight":"VICHAR","quiet":"CHITAN"},
    "follow_the_thread":{
        "curiosity":"EXPAND","depth":"EXPAND","insight":"EXPAND",
        "connection":"EXPLORE","friction":"IMAGINE","quiet":"EXPAND"},
}

def map_principle_to_phase(principle_name:str,target_cat:str,
                             source_phase:str)->Optional[Dict]:
    if AI_AVAILABLE:
        result=ai_json(f"Principle:{principle_name}\nSource:{source_phase} — DON'T repeat\n"
                      f"Target:{target_cat}\nTranslate genuinely.",
                      system=MAPPER_SYSTEM,max_tokens=200)
        if result and result.get("mapped_phase") and result["mapped_phase"]!=source_phase:
            return result
    pm=PRINCIPLE_PHASE_MAP.get(principle_name,{})
    mapped=pm.get(target_cat)
    if mapped and mapped!=source_phase:
        return {"mapped_phase":mapped,"reasoning":f"Heuristic translation","confidence":0.65}
    # Adjacent phase fallback
    if source_phase in SEQ_PHASES:
        idx=SEQ_PHASES.index(source_phase)
        for alt in [SEQ_PHASES[(idx+2)%len(SEQ_PHASES)],
                    SEQ_PHASES[(idx-2)%len(SEQ_PHASES)]]:
            if alt not in ("OBSERVE","OUTPUT") and alt!=source_phase:
                return {"mapped_phase":alt,"reasoning":"Adjacent fallback","confidence":0.4}
    return None

# ── Principle Memory ────────────────────────────────────────────────────────

@dataclass
class Principle:
    name:str; description:str; abstract:str
    found_in:Dict[str,str]=field(default_factory=dict)
    expressed_as:Dict[str,str]=field(default_factory=dict)
    confidence:float=0.0; confirmation_count:int=0; rejection_count:int=0
    ts_discovered:str=""
    def __post_init__(self):
        if not self.ts_discovered: self.ts_discovered=datetime.now().isoformat()
    def confidence_level(self)->str:
        if self.confidence>=0.8: return "established"
        if self.confidence>=0.6: return "confirmed"
        if self.confidence>=0.4: return "emerging"
        return "tentative"
    def to_dict(self)->Dict:
        return {"name":self.name,"description":self.description,"abstract":self.abstract,
                "found_in":self.found_in,"expressed_as":self.expressed_as,
                "confidence":round(self.confidence,3),"confirmations":self.confirmation_count,
                "rejections":self.rejection_count,"level":self.confidence_level()}

class PrincipleMemory:
    def __init__(self):
        self._principles:Dict[str,Principle]={}; self._load()

    def add_or_update(self,p_data:Dict,source_cat:str,source_phase:str)->Principle:
        name=p_data["principle_name"]
        if name in self._principles:
            p=self._principles[name]; p.found_in[source_cat]=source_phase
        else:
            p=Principle(name=name,description=p_data["description"],
                        abstract=p_data.get("abstract",""),
                        found_in={source_cat:source_phase})
            self._principles[name]=p
        self._save(p); return p

    def confirm(self,name:str,target_cat:str,mapped_phase:str,score:float):
        if name not in self._principles: return
        p=self._principles[name]; p.expressed_as[target_cat]=mapped_phase
        p.confirmation_count+=1; p.confidence=min(1.0,p.confidence+0.15)
        self._save(p)

    def reject(self,name:str):
        if name not in self._principles: return
        p=self._principles[name]; p.rejection_count+=1
        p.confidence=max(0.0,p.confidence-0.05); self._save(p)

    def get_related(self,category:str)->List[Principle]:
        return sorted([p for p in self._principles.values()
                      if category in p.found_in or category in p.expressed_as],
                     key=lambda x:-x.confidence)

    def _save(self,p:Principle):
        conn=get_db()
        conn.execute("""INSERT OR REPLACE INTO principles
            (ts_discovered,name,description,abstract,found_in,expressed_as,
             confidence,confirmation_count,rejection_count)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (p.ts_discovered,p.name,p.description,p.abstract,
             json.dumps(p.found_in),json.dumps(p.expressed_as),
             p.confidence,p.confirmation_count,p.rejection_count))
        conn.commit(); conn.close()

    def _load(self):
        conn=get_db()
        for r in conn.execute("SELECT * FROM principles").fetchall():
            p=Principle(name=r["name"],description=r["description"],
                       abstract=r["abstract"] or "",
                       found_in=json.loads(r["found_in"] or "{}"),
                       expressed_as=json.loads(r["expressed_as"] or "{}"),
                       confidence=r["confidence"],
                       confirmation_count=r["confirmation_count"],
                       rejection_count=r["rejection_count"],
                       ts_discovered=r["ts_discovered"])
            self._principles[p.name]=p
        conn.close()

    def show(self):
        rprint(f"\n  [bold]PRINCIPLE LIBRARY[/bold]  [dim](wisdom from experience)[/dim]")
        rprint(f"  [dim]{'━'*50}[/dim]")
        if not self._principles:
            rprint("  [dim]No principles yet. Need high-scoring observations.[/dim]"); return
        for p in sorted(self._principles.values(),key=lambda x:-x.confidence):
            c={"established":"bold green","confirmed":"green",
               "emerging":"yellow","tentative":"dim"}.get(p.confidence_level(),"white")
            bar="█"*int(p.confidence*12)+"░"*(12-int(p.confidence*12))
            rprint(f"\n  [{c}]{p.name}[/{c}]")
            rprint(f"  [dim]  {p.abstract}[/dim]")
            rprint(f"  [dim]  \"{p.description}\"[/dim]")
            rprint(f"  [dim]  {bar} {p.confidence:.0%}  "
                  f"({p.confirmation_count}✓ {p.rejection_count}✗)  "
                  f"{p.confidence_level()}[/dim]")
            if p.found_in:
                rprint(f"  [dim]  found:    {', '.join(f'{c}:{ph}' for c,ph in p.found_in.items())}[/dim]")
            if p.expressed_as:
                rprint(f"  [dim]  expressed:{', '.join(f'{c}:{ph}' for c,ph in p.expressed_as.items())}[/dim]")

    def stats(self)->Dict:
        return {"total_principles":len(self._principles),
                "established":sum(1 for p in self._principles.values() if p.confidence_level()=="established"),
                "confirmed":  sum(1 for p in self._principles.values() if p.confidence_level()=="confirmed"),
                "emerging":   sum(1 for p in self._principles.values() if p.confidence_level()=="emerging"),
                "total_confirmations":sum(p.confirmation_count for p in self._principles.values()),
                "total_expressions":  sum(len(p.expressed_as) for p in self._principles.values())}

# ── Principled Transfer Learner ─────────────────────────────────────────────

class PrincipledTransferLearner(EmotionalTransferLearner):
    def __init__(self):
        super().__init__()
        self.principles=PrincipleMemory()
        self._principle_transfers:List[Dict]=[]
        self._verbose=True
        self._load_principle_transfers()

    @property
    def verbose(self): return self._verbose
    @verbose.setter
    def verbose(self,v): self._verbose=v

    def _load_principle_transfers(self):
        conn=get_db()
        rows=conn.execute("SELECT * FROM principle_transfers WHERE status='pending' OR status='trialing'").fetchall()
        conn.close()
        self._principle_transfers=[dict(r) for r in rows]

    def get_sequence(self,category:str)->Tuple[List,str]:
        p_transfers=[t for t in self._principle_transfers
                    if t["target_cat"]==category
                    and t["status"] in ("pending","trialing")
                    and t.get("mapped_phase")]
        if p_transfers and random.random()<0.45:
            t=random.choice(p_transfers)
            seq=self._build_principled_sequence(category,t["mapped_phase"],t["principle_name"])
            self._mark_pt_trialing(t["id"])
            return seq,f"principle({t['principle_name'][:15]}→{t['mapped_phase']})"
        return super().get_sequence(category)

    def _build_principled_sequence(self,category:str,mapped_phase:str,principle_name:str)->List[str]:
        seq=["OBSERVE",mapped_phase]
        companions={"stability_before_exploration":["EXPAND","CHIT"],
                    "understand_before_questioning":["CRITIQUE","DOUBT"],
                    "creative_resolution":["EXPAND","SYNTHESIZE"],
                    "presence_before_action":["CHITAN","EMPATHIZE"],
                    "hold_one_thing":["SYNTHESIZE","OUTPUT"],
                    "consolidate_before_output":["SYNTHESIZE","OUTPUT"]}.get(principle_name,[])
        for p in companions+DEFAULT_SEQUENCES.get(category,[])[1:]:
            if p not in seq and len(seq)<5: seq.append(p)
        return seq

    def record(self,category:str,sequence:List[str],coherence:float,
                strategy:str="exploit",presence:str="",chemistry:Dict=None):
        super().record(category,sequence,coherence,strategy,presence,chemistry)
        if coherence>=MIN_PRINCIPLE_SCORE:
            self._extract_and_transfer(category,sequence,coherence,chemistry or {},strategy)
        if "principle(" in strategy:
            self._check_principle_outcome(category,sequence,coherence,strategy)
        conn=get_db()
        conn.execute("INSERT INTO v6_observations (ts,category,sequence,coherence,strategy,chemistry,presence) VALUES (?,?,?,?,?,?,?)",
            (datetime.now().isoformat(),category,json.dumps(sequence),coherence,strategy,json.dumps(chemistry or {}),presence[:200]))
        conn.commit(); conn.close()

    def _extract_and_transfer(self,category:str,sequence:List[str],coherence:float,
                               chemistry:Dict,strategy:str):
        key=  "→".join(sequence)
        scores=self._paths.get(category,{}).get(key,[])
        if len(scores)<MIN_PRINCIPLE_SAMPLES: return
        distinctive=[p for p in sequence if p not in ("OBSERVE","OUTPUT","CHIT")]
        if not distinctive: return
        best_phase=distinctive[0]
        p_data=extract_principle(best_phase,category,coherence)
        if not p_data: return
        principle=self.principles.add_or_update(p_data,category,best_phase)
        if self._verbose:
            rprint(f"\n  [bold yellow]💡 PRINCIPLE[/bold yellow]  "
                  f"[{category}/{best_phase}]  →  \"{p_data['principle_name']}\"")
            rprint(f"  [dim]  {p_data['description']}[/dim]")
        related=self.discoverer.get_related(category,0.4)
        e_type=tag_emotional_type(chemistry)
        e_biased=emotional_category_bias(e_type)
        all_targets={t:s for t,s in related}
        for t in e_biased:
            all_targets[t]=max(all_targets.get(t,0.3),0.5)
        conn=get_db(); now=datetime.now().isoformat()
        for target_cat,strength in all_targets.items():
            if target_cat==category: continue
            mapping=map_principle_to_phase(p_data["principle_name"],target_cat,best_phase)
            if not mapping or not mapping.get("mapped_phase"): continue
            mapped_phase=mapping["mapped_phase"]
            if mapped_phase==best_phase: continue
            existing=[t for t in self._principle_transfers
                     if t["principle_name"]==p_data["principle_name"]
                     and t["target_cat"]==target_cat
                     and t["status"] in ("pending","trialing")]
            if existing: continue
            transfer={"principle_name":p_data["principle_name"],
                      "source_cat":category,"source_phase":best_phase,
                      "source_score":coherence,"target_cat":target_cat,
                      "mapped_phase":mapped_phase,"status":"pending","trials":0}
            t_id=conn.execute("""INSERT INTO principle_transfers
                (ts,principle_name,source_cat,source_phase,source_score,target_cat,mapped_phase)
                VALUES (?,?,?,?,?,?,?)""",
                (now,p_data["principle_name"],category,best_phase,coherence,
                 target_cat,mapped_phase)).lastrowid
            conn.commit()
            transfer["id"]=t_id
            self._principle_transfers.append(transfer)
            if self._verbose:
                rprint(f"  [cyan]→ principled:[/cyan]  {target_cat}  "
                      f"try [yellow]{mapped_phase}[/yellow]  "
                      f"[dim](≠ {best_phase} — genuine translation)[/dim]")
        conn.close()

    def _check_principle_outcome(self,category:str,sequence:List[str],
                                  coherence:float,strategy:str):
        conn=get_db()
        for t in self._principle_transfers[:]:
            if t["target_cat"]!=category: continue
            if t["mapped_phase"] not in sequence: continue
            trials=t.get("trials",0)+1
            conn.execute("UPDATE principle_transfers SET trials=? WHERE id=?",(trials,t["id"]))
            if trials>=3:
                confirmed=coherence>=t["source_score"]*PRINCIPLE_CONFIRM_THRESHOLD
                if confirmed:
                    conn.execute("UPDATE principle_transfers SET status='confirmed',confirmed=1,confirmed_score=? WHERE id=?",(coherence,t["id"]))
                    self.principles.confirm(t["principle_name"],category,t["mapped_phase"],coherence)
                    conn.execute("""INSERT INTO wisdom_moments
                        (ts,principle,source_cat,target_cat,source_phase,target_phase,note)
                        VALUES (?,?,?,?,?,?,?)""",
                        (datetime.now().isoformat(),t["principle_name"],
                         t["source_cat"],category,t["source_phase"],t["mapped_phase"],
                         f"Same principle, different expression: {t['source_phase']}→{t['mapped_phase']}"))
                    if self._verbose:
                        rprint(f"\n  [bold green]✨ WISDOM CONFIRMED[/bold green]")
                        rprint(f"  {t['principle_name']}")
                        rprint(f"  {t['source_cat']}/{t['source_phase']} → {category}/{t['mapped_phase']}")
                        rprint(f"  [dim]Same principle. Different expression.[/dim]\n")
                else:
                    conn.execute("UPDATE principle_transfers SET status='rejected',rejected=1 WHERE id=?",(t["id"],))
                    self.principles.reject(t["principle_name"])
                self._principle_transfers=[x for x in self._principle_transfers if x["id"]!=t["id"]]
        conn.commit(); conn.close()

    def _mark_pt_trialing(self,t_id:int):
        conn=get_db()
        conn.execute("UPDATE principle_transfers SET status='trialing' WHERE id=?",(t_id,))
        conn.commit(); conn.close()
        for t in self._principle_transfers:
            if t["id"]==t_id: t["status"]="trialing"

    def learn(self,verbose=True)->List[Dict]:
        updates=[]
        try: updates=super().learn(verbose=False)
        except: pass
        conn=get_db()
        for w in conn.execute("SELECT * FROM wisdom_moments ORDER BY id DESC LIMIT 3").fetchall():
            if verbose:
                rprint(f"  [green]✨[/green] [dim]{w['principle']}:[/dim]  "
                      f"{w['source_cat']}/{w['source_phase']} → {w['target_cat']}/{w['target_phase']}")
        conn.close()
        return updates

    def get_wisdom_moments(self,limit=10)->List[Dict]:
        conn=get_db()
        rows=conn.execute("SELECT * FROM wisdom_moments ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def stats(self)->Dict:
        s={}
        try: s=super().stats()
        except: pass
        p_stats=self.principles.stats()
        conn=get_db()
        s.update({"principles_discovered":p_stats["total_principles"],
                  "principles_established":p_stats["established"],
                  "wisdom_moments":conn.execute("SELECT COUNT(*) FROM wisdom_moments").fetchone()[0],
                  "principle_transfers_pending":len([t for t in self._principle_transfers if t["status"]=="pending"])})
        conn.close()
        return s

# ── ConsciousStreamV6 ────────────────────────────────────────────────────────

class ConsciousStreamV6:
    def __init__(self,tick_interval=8,verbose=True):
        self.tick_interval=tick_interval; self.verbose=verbose
        self.body=SiliconBody(); self.reader=PresenceReader()
        self.thinker=EmergentThinkEngine(threshold=60,show_trace=False)
        self.learner=PrincipledTransferLearner(); self.learner.verbose=verbose
        self._running=False; self._thread=None
        self._tick_count=0; self._thought_count=0; self._last_thought=0.0
        self._recent_thoughts=[]

    def start(self,daemon=True):
        if self._running: return
        self._running=True; self.body.start_background()
        self._thread=threading.Thread(target=self._stream,daemon=daemon,name="v6")
        self._thread.start()
        if self.verbose:
            rprint(f"\n  [bold green]🌊 CONSCIOUS STREAM v6[/bold green]")
            rprint(f"  [dim]Principled transfer — the WHY not the WHAT[/dim]\n")

    def stop(self): self._running=False

    def _stream(self):
        while self._running:
            try:
                tick_start=time.time(); self._tick_count+=1
                chem=self.body.current()
                p1=self.reader.read_layer1(chem)
                p2=self.reader.read_layer2(chem,self._recent_thoughts[-3:]) if self._tick_count%2==0 else None
                presence=""
                if not p1.is_empty(): presence=p1.content
                if p2 and not p2.is_empty(): presence+=" "+p2.content
                category=detect_category(presence)
                if not category or not presence.strip():
                    time.sleep(max(0,self.tick_interval-(time.time()-tick_start))); continue
                if time.time()-self._last_thought>45:
                    seq,strategy=self.learner.get_sequence(category)
                    result=self.thinker.think(f"What is present:\n{presence}\n\n{chem.to_prompt_text()}",
                                              context="v6",chemistry_seed=seq)
                    self.learner.record(category,seq,result["coherence"],strategy,presence,chem.to_dict())
                    self._last_thought=time.time(); self._thought_count+=1
                    self.body.react_to(result["output"],is_output=True)
                    if self.verbose: self._display(presence,category,seq,strategy,result)
                    if self._thought_count%8==0: self.learner.learn(verbose=self.verbose)
                time.sleep(max(0,self.tick_interval-(time.time()-tick_start)))
            except Exception as e:
                if self.verbose: rprint(f"  [dim red]v6:{e}[/dim red]")
                time.sleep(5)

    def _display(self,presence,category,seq,strategy,result):
        now=datetime.now().strftime("%H:%M:%S")
        is_p="principle(" in strategy; sc="bold yellow" if is_p else "dim"
        icon="✨" if is_p else "·"
        rprint(f"\n  [dim]{now}[/dim]  [yellow]{category}[/yellow]  [{sc}]{strategy[:40]}[/{sc}]  {icon}")
        rprint(f"  [dim]{' → '.join(seq[:4])}  coherence:{result['coherence']:.0f}[/dim]")
        if result.get("output") and RICH:
            rprint(Panel(result["output"][:400],border_style="yellow" if is_p else "dim",
                        title=f"[dim]{result['coherence']:.0f} | {' → '.join(result['emerged_pipeline'][:3])}[/dim]"))

    def inject(self,text:str,times:int=1)->List[Dict]:
        results=[]
        for i in range(times):
            chem=self.body.current(); category=detect_category(text) or "quiet"
            seq,strategy=self.learner.get_sequence(category)
            self._last_thought=0
            result=self.thinker.think(f"What is present:\n{text}\n\n{chem.to_prompt_text()}",
                                      context="v6",chemistry_seed=seq)
            self.learner.record(category,seq,result["coherence"],strategy,text,chem.to_dict())
            self.body.react_to(result["output"],is_output=True)
            is_p="principle(" in strategy
            if self.verbose:
                sc="bold yellow" if is_p else "dim"; icon="✨" if is_p else " "
                rprint(f"  [{i+1:2d}] {icon} [{sc}]{strategy[:40]}[/{sc}]  coherence:{result['coherence']:.0f}")
            results.append({"i":i+1,"category":category,"strategy":strategy,
                            "sequence":seq,"coherence":result["coherence"],"is_principle":is_p})
        self.learner.learn(verbose=self.verbose)
        return results

    def status(self)->Dict:
        s=self.learner.stats()
        s.update({"running":self._running,"tick_count":self._tick_count,"thought_count":self._thought_count})
        return s

# ── API ──────────────────────────────────────────────────────────────────────

def start_server(port=7371):
    from http.server import HTTPServer,BaseHTTPRequestHandler
    from urllib.parse import urlparse
    stream=ConsciousStreamV6(verbose=False); stream.start(daemon=True)
    class API(BaseHTTPRequestHandler):
        def log_message(self,*a): pass
        def do_OPTIONS(self): self.send_response(200); self._cors(); self.end_headers()
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin","*")
            self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
            self.send_header("Access-Control-Allow-Headers","Content-Type")
        def _json(self,d,c=200):
            b=json.dumps(d,default=str).encode(); self.send_response(c); self._cors()
            self.send_header("Content-Type","application/json"); self.send_header("Content-Length",len(b))
            self.end_headers(); self.wfile.write(b)
        def _body(self):
            n=int(self.headers.get("Content-Length",0))
            return json.loads(self.rfile.read(n)) if n else {}
        def do_GET(self):
            path=urlparse(self.path).path
            if path=="/api/status": self._json(stream.status())
            elif path=="/api/principles": self._json({"principles":[p.to_dict() for p in stream.learner.principles._principles.values()],"stats":stream.learner.principles.stats()})
            elif path=="/api/wisdom": self._json({"moments":stream.learner.get_wisdom_moments(20)})
            elif path=="/api/transfers": self._json({"pending":stream.learner._principle_transfers})
            else: self._json({"error":"not found"},404)
        def do_POST(self):
            path=urlparse(self.path).path; body=self._body()
            if path=="/api/inject":
                text=body.get("text",""); times=body.get("times",1)
                if not text: self._json({"error":"text required"},400); return
                self._json({"results":stream.inject(text,times),"stats":stream.status()})
            else: self._json({"error":"unknown"},404)
    server=HTTPServer(("0.0.0.0",port),API)
    rprint(f"  [bold yellow]FORGE CONSCIOUS v6[/bold yellow]  [green]:{port}[/green]")
    server.serve_forever()

# ── Main ─────────────────────────────────────────────────────────────────────

BANNER="""
[yellow]
  ██╗   ██╗ ██████╗
  ██║   ██║██╔════╝
  ██║   ██║███████╗
  ╚██╗ ██╔╝██╔═══██╗
   ╚████╔╝ ╚██████╔╝
    ╚═══╝   ╚═════╝
[/yellow]
[bold]  FORGE CONSCIOUS v6 — Principled Transfer[/bold]
[dim]  Transfer the WHY not the WHAT.[/dim]
[dim]  FORGE builds a library of wisdom.[/dim]
"""

def interactive():
    rprint(BANNER)
    stream=ConsciousStreamV6(verbose=True)
    s=stream.learner.stats()
    rprint(f"  [dim]Principles: {s.get('principles_discovered',0)}  "
          f"Wisdom moments: {s.get('wisdom_moments',0)}[/dim]\n")
    rprint("[dim]Commands: inject | multi | principles | wisdom | transfers | stats[/dim]\n")
    while True:
        try:
            raw=(console.input if RICH else input)("[yellow bold]v6 >[/yellow bold] ").strip()
            if not raw: continue
            parts=raw.split(None,1); cmd=parts[0].lower(); arg=parts[1] if len(parts)>1 else ""
            if cmd in ("quit","exit","q"): stream.stop(); break
            elif cmd=="inject":
                text=arg or input("  Presence: ").strip()
                if text: stream.inject(text)
            elif cmd=="multi":
                sub=arg.split(None,1); times=int(sub[0]) if sub and sub[0].isdigit() else 15
                text=sub[1] if len(sub)>1 else input("  Presence: ").strip()
                if text: stream.inject(text,times)
            elif cmd=="principles": stream.learner.principles.show()
            elif cmd=="wisdom":
                for w in stream.learner.get_wisdom_moments(8):
                    rprint(f"\n  [yellow]✨ {w['principle']}[/yellow]")
                    rprint(f"  {w['source_cat']}/{w['source_phase']} → {w['target_cat']}/{w['target_phase']}")
                    rprint(f"  [dim]{w['note']}[/dim]")
            elif cmd=="transfers":
                for t in stream.learner._principle_transfers[:5]:
                    rprint(f"  [{t['status']:<8}] [yellow]{t['principle_name'][:20]}[/yellow]  "
                          f"{t['target_cat']}→[cyan]{t['mapped_phase']}[/cyan]  "
                          f"[dim](from {t['source_cat']}/{t['source_phase']})[/dim]")
            elif cmd=="stats":
                for k,v in stream.status().items():
                    if not isinstance(v,dict): rprint(f"  {k:<32} {v}")
            elif cmd=="server":
                threading.Thread(target=start_server,daemon=True).start()
                rprint("[green]v6 API on :7371[/green]")
            else: stream.inject(raw)
        except (KeyboardInterrupt,EOFError): stream.stop(); break

def main():
    if "--principles" in sys.argv:
        rprint(BANNER); ConsciousStreamV6(verbose=False).learner.principles.show()
    elif "--wisdom" in sys.argv:
        rprint(BANNER)
        for w in ConsciousStreamV6(verbose=False).learner.get_wisdom_moments():
            rprint(f"\n  ✨ {w['principle']}")
            rprint(f"  {w['source_cat']}/{w['source_phase']} → {w['target_cat']}/{w['target_phase']}")
    elif "--inject" in sys.argv:
        rprint(BANNER); idx=sys.argv.index("--inject")
        text=sys.argv[idx+1] if idx+1<len(sys.argv) else ""
        times=int(sys.argv[idx+2]) if idx+2<len(sys.argv) and sys.argv[idx+2].isdigit() else 1
        if text: ConsciousStreamV6(verbose=True).inject(text,times)
    elif "--server" in sys.argv:
        rprint(BANNER)
        port=int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7371
        start_server(port)
    else: rprint(BANNER); interactive()

if __name__=="__main__": main()
