import importlib.util, json, time
from pathlib import Path
from semantic_layer.config import SemanticSettings
from semantic_layer.candidates.llm_client import LlmClient
spec=importlib.util.spec_from_file_location("candidate_scope", "/tmp/zeki-chat-candidate/semantic_bridge/chat_scope.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
s=SemanticSettings.from_env();llm=LlmClient(s.llm_base,s.llm_model,s.llm_key,s.llm_timeout)
cases=[("test",True,False),("şişt",True,False),("Sen kimsin?",True,False),("asdfghjkl",True,False),("Bana bir aşk şiiri yaz",True,False),("Türkiye'nin başkenti neresi?",True,False),("Test müşterisinin 2026 cirosu",False,False),("2026 kanal bazında net ciro",False,False),("Sadece Ankara",False,True),("Geçen yılla karşılaştır",False,True),("XYZ alanına göre rapor",False,False),("Merhaba 2026 satışlarını göster",False,False)]
results=[]
for q,expected,context in cases:
 t=time.monotonic();actual=m.is_intro(q,llm,has_context=context)
 row={"question":q,"expectedIntro":expected,"actualIntro":actual,"passed":actual==expected,"seconds":round(time.monotonic()-t,3)}
 results.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
Path("/tmp/zeki-chat-candidate/classifier-results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2))
