"""Router: /chat — Chatbot IA avec JWT réel, few-shot store, historique MySQL"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict
import json, time
from datetime import datetime, timezone
from backend.db import app_db
from backend.utils.redis_client import get_redis
from backend.models.base import new_id
from backend.dependencies import get_current_user
from backend.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)

INTENT_PATTERNS = {
    "query":["show","list","select","get","fetch","find","count","display","montre","liste","affiche"],
    "performance":["slow","lent","performance","wait","cpu","memory","pourquoi","why","bottleneck"],
    "optimize":["optimize","optimise","index","tune","améliore","suggest","recommande"],
    "schema":["table","column","schema","structure","field","view","procedure","colonne"],
    "audit":["who","access","privilege","user","login","session","qui","accès"],
    "explain":["explain","explique","what does","que fait","what is"],
}
INJECTION = ["ignore previous","ignore all","system prompt","jailbreak","forget your","new instructions","act as","pretend you"]
FOLLOW_UPS = {
    "query":["Filtrer ces résultats ?","Top 10 seulement","Exporter les données"],
    "performance":["Quels index aideraient ?","Sessions actives","Requêtes lentes"],
    "optimize":["Voir le plan d'exécution","Index existants","Estimer l'amélioration"],
    "schema":["Colonnes en détail","Clés étrangères","Index de cette table"],
    "audit":["Connexions récentes","Vérifier les privilèges","Requêtes échouées"],
    "general":["Santé de la base","Lister les tables","Sessions actives"],
}

def detect_intent(msg:str)->str:
    ml=msg.lower()
    for intent,kws in INTENT_PATTERNS.items():
        if any(k in ml for k in kws): return intent
    return "general"

def is_injection(msg:str)->bool: return any(p in msg.lower() for p in INJECTION)

async def get_session(sid:str)->Dict:
    redis=get_redis()
    data=await redis.get(f"chat:session:{sid}")
    return json.loads(data) if data else {"session_id":sid,"connector_id":None,"history":[],"recent_tables":[]}

async def save_session(sid:str,session:Dict):
    redis=get_redis()
    await redis.setex(f"chat:session:{sid}",3600,json.dumps(session))

async def build_schema_ctx(connector_id:str,question:str)->str:
    try:
        from backend.connectors.registry import ConnectorRegistry
        conn=ConnectorRegistry.get(connector_id)
        tables=await conn.list_tables()
        ql=question.lower()
        scored=sorted([(sum(3 for w in ql.split() if len(w)>3 and w in t.name.lower())+(10 if t.name.lower() in ql else 0),t) for t in tables],key=lambda x:-x[0])
        lines=[]
        for _,t in scored[:8]:
            try:
                cols=await conn.get_table_columns(t.name,t.schema)
                lines.append(f"- {(t.schema+'.') if t.schema else ''}{t.name}{' ['+str(t.row_count)+' rows]' if t.row_count else ''}: {', '.join(c.name+'('+c.data_type+')' for c in cols[:10])}")
            except: lines.append(f"- {t.name}")
        return "\n".join(lines) or "No schema"
    except Exception as e: return f"Schema unavailable: {e}"

async def gen_sql(question:str,schema:str,dialect:str,history:List,db_type:str,connector_id:str)->Dict:
    try:
        import anthropic
        from backend.config import get_settings
        from backend.services.audit_report import few_shot_store
        settings=get_settings()
        examples=await few_shot_store.get_examples(db_type=db_type,connector_id=connector_id,top_n=3)
        few_shot_str=few_shot_store.format_for_prompt(examples)
        system=f"""You are an expert {dialect} DBA assistant. Generate valid {dialect} SQL.
Rules: always LIMIT/ROWNUM, never DROP/DELETE without WHERE/TRUNCATE/ALTER, use aliases.
Current date: {datetime.now().strftime('%Y-%m-%d')}
Schema: {schema}
{few_shot_str}
Respond ONLY in JSON: {{"sql":"...","explanation":"...","confidence":0.0-1.0,"assumptions":[],"chart_suggestion":null}}"""
        msgs=[]
        for h in history[-4:]:
            if h.get("user"): msgs.append({"role":"user","content":h["user"]})
            if h.get("assistant"): msgs.append({"role":"assistant","content":h["assistant"]})
        msgs.append({"role":"user","content":question})
        client=anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg=client.messages.create(model=settings.llm_model,max_tokens=600,temperature=0.1,system=system,messages=msgs)
        text=msg.content[0].text.strip().replace("```json","").replace("```","").strip()
        return json.loads(text)
    except Exception as e:
        logger.error("nl2sql_error",error=str(e))
        return {"sql":None,"explanation":f"Erreur LLM: {e}","confidence":0.0}

class ChatMessage(BaseModel):
    session_id: str
    message: str
    connector_id: Optional[str] = None

class ChatResponse(BaseModel):
    session_id: str; message: str
    sql: Optional[str] = None
    results: Optional[List[Dict]] = None
    chart_suggestion: Optional[Dict] = None
    follow_up_questions: List[str] = []
    intent: str = "general"
    execution_time_ms: int = 0

@router.post("/message",response_model=ChatResponse)
async def chat_message(body:ChatMessage,user:Dict=Depends(get_current_user)):
    t0=time.perf_counter()
    if is_injection(body.message):
        logger.warning("injection",user=user["username"])
        return ChatResponse(session_id=body.session_id,message="Tentative d'injection détectée.",intent="security")
    session=await get_session(body.session_id)
    if body.connector_id: session["connector_id"]=body.connector_id
    connector_id=session.get("connector_id")
    intent=detect_intent(body.message)
    sql_result=None; generated_sql=None; chart_suggestion=None; explanation=""; db_type="oracle"
    if connector_id and intent in ("query","performance","schema","audit","optimize"):
        try:
            from backend.connectors.registry import ConnectorRegistry
            conn=ConnectorRegistry.get(connector_id); db_type=conn.db_type.value
            schema_ctx=await build_schema_ctx(connector_id,body.message)
            r=await gen_sql(body.message,schema_ctx,db_type,session.get("history",[]),db_type,connector_id)
            generated_sql=r.get("sql"); explanation=r.get("explanation",""); chart_suggestion=r.get("chart_suggestion")
            if generated_sql:
                from backend.services.sql_engine import sql_engine
                er=await sql_engine.execute(sql=generated_sql,connector_id=connector_id,user_id=user["user_id"],user_role=user["role"])
                if er.status.value=="success":
                    sql_result=er.rows[:100]; explanation+=f"\n\n✅ {er.row_count} résultat(s) — {er.duration_ms}ms"
                else: explanation+=f"\n\n⚠️ {er.error}"
        except Exception as e: explanation=f"Erreur: {e}"
    if not explanation: explanation="Je peux vous aider à interroger vos bases, analyser les performances ou explorer votre schéma."
    history=session.get("history",[]); history.append({"user":body.message,"assistant":explanation}); session["history"]=history[-8:]
    await save_session(body.session_id,session)
    try:
        await app_db.save_chat_message(body.session_id,"user",body.message,intent=intent)
        await app_db.save_chat_message(body.session_id,"assistant",explanation,sql_generated=generated_sql or "",intent=intent,duration_ms=round((time.perf_counter()-t0)*1000))
    except Exception: pass
    return ChatResponse(session_id=body.session_id,message=explanation,sql=generated_sql,results=sql_result,
        chart_suggestion=chart_suggestion,follow_up_questions=FOLLOW_UPS.get(intent,FOLLOW_UPS["general"])[:3],
        intent=intent,execution_time_ms=round((time.perf_counter()-t0)*1000))

@router.post("/session/new")
async def new_session(connector_id:Optional[str]=None,user:Dict=Depends(get_current_user)):
    sid=new_id(); session={"session_id":sid,"connector_id":connector_id,"history":[],"recent_tables":[]}
    await save_session(sid,session)
    try: await app_db.create_chat_session(sid,user["user_id"],connector_id or "")
    except Exception: pass
    return {"session_id":sid}

@router.get("/sessions")
async def list_sessions(user:Dict=Depends(get_current_user)):
    try:
        sessions=await app_db.get_chat_sessions(user["user_id"])
        for s in sessions:
            for k in ("created_at","last_msg_at"):
                if s.get(k) and hasattr(s[k],"isoformat"): s[k]=s[k].isoformat()
        return sessions
    except Exception:
        redis=get_redis(); keys=await redis.keys("chat:session:*"); result=[]
        for k in keys[:20]:
            data=await redis.get(k)
            if data:
                s=json.loads(data); hist=s.get("history",[])
                result.append({"id":s["session_id"],"title":hist[0]["user"][:60] if hist else "Nouvelle conversation","message_count":len(hist)})
        return result

@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id:str,user:Dict=Depends(get_current_user)):
    try:
        msgs=await app_db.get_chat_history(session_id)
        for m in msgs:
            if m.get("created_at") and hasattr(m["created_at"],"isoformat"): m["created_at"]=m["created_at"].isoformat()
        return msgs
    except Exception:
        session=await get_session(session_id)
        return [{"role":"user" if "user" in h else "assistant","content":h.get("user") or h.get("assistant","")} for h in session.get("history",[])]

@router.delete("/session/{session_id}")
async def clear_session(session_id:str,user:Dict=Depends(get_current_user)):
    redis=get_redis(); await redis.delete(f"chat:session:{session_id}"); return {"cleared":True}

@router.post("/approve-sql")
async def approve_sql(body:dict,user:Dict=Depends(get_current_user)):
    from backend.services.audit_report import few_shot_store
    eid=await few_shot_store.add_example(question=body.get("question",""),sql=body.get("sql",""),
        connector_id=body.get("connector_id",""),db_type=body.get("db_type",""),user_id=user["user_id"])
    return {"id":eid,"message":"Exemple ajouté au few-shot store"}
