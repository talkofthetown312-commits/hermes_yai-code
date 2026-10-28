"""Offline model preflight and disabled GPU preparation. No training executor."""
import json
import os
from pathlib import Path
import struct
import time
from evolution import Denied, file_hash, digest

def memory_available_mib():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'): return int(line.split()[1])/1024
    raise Denied('Memory telemetry unavailable')

def gguf_metadata(path):
    types={0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}
    result={}
    with Path(path).open('rb') as f:
        def number(fmt):
            n=struct.calcsize('<'+fmt); raw=f.read(n)
            if len(raw)!=n: raise ValueError('Truncated GGUF')
            return struct.unpack('<'+fmt,raw)[0]
        def string(keep=True):
            n=number('Q')
            if n>16777216: raise ValueError('GGUF string budget')
            if keep:
                raw=f.read(n)
                if len(raw)!=n: raise ValueError('Truncated GGUF string')
                return raw.decode()
            f.seek(n,1)
        def value(t,keep=True):
            if t in types: return number(types[t])
            if t==8: return string(keep)
            if t==9:
                subtype=number('I'); n=number('Q')
                if n>1000000 or subtype==9: raise ValueError('GGUF array budget')
                for _ in range(n): value(subtype,False)
                return None
            raise ValueError('Unsupported GGUF metadata type')
        if f.read(4)!=b'GGUF' or number('I') not in (2,3): raise ValueError('Invalid GGUF')
        tensors=number('Q'); count=number('Q')
        if count>2048 or tensors>10000: raise ValueError('GGUF metadata budget')
        for _ in range(count):
            key=string(); t=number('I'); keep=key in {'general.architecture','general.name','general.file_type','qwen2.block_count','qwen2.embedding_length','tokenizer.chat_template'}
            v=value(t,keep)
            if keep: result[key]=v
    if 'tokenizer.chat_template' in result: result['chat_template_sha256']=digest(result.pop('tokenizer.chat_template'))
    return result

class QwenProbe:
    def __init__(self,path,expected_hash): self.path=Path(path); self.expected_hash=expected_hash
    def validate(self,requested):
        if Path(requested)!=self.path or self.path.is_symlink() or self.path.name!='qwen.gguf' or file_hash(self.path)!=self.expected_hash: raise Denied('Only unchanged registered existing 1.5B model allowed')
        m=gguf_metadata(self.path)
        if m.get('general.architecture')!='qwen2' or m.get('qwen2.embedding_length')!=1536 or m.get('qwen2.block_count')!=28: raise Denied('Not the approved 1.5B architecture')
        return m
    @staticmethod
    def arguments(binary,path,prompt):
        return [str(binary),'-m',str(path),'--offline','--single-turn','--no-display-prompt','--no-warmup','-t','2','-tb','2','-c','512','-b','64','-ub','32','-n','32','-ngl','0','-p',prompt]
    def preflight(self,available=None,temperature=None,battery=None,occupied=False):
        available=memory_available_mib() if available is None else available
        reasons=[]
        if available<2560: reasons.append('available_memory_below_2560_MiB')
        if temperature is not None and temperature>=42: reasons.append('thermal_limit')
        if battery is not None and battery<25: reasons.append('battery_limit')
        if occupied: reasons.append('occupied_resources')
        return {'eligible':not reasons,'reasons':reasons,'available_MiB':round(available,1),'thermal':'unknown' if temperature is None else temperature,'battery':'unknown' if battery is None else battery,'sampled_at':time.time(),'actions_taken':[]}
    def run(self,approved=False):
        # Separate Gate B: Phase 1 implementation approval does not start model inference.
        if approved is not True: return {'status':'NOT_RUN_SEPARATE_INFERENCE_APPROVAL_REQUIRED','preflight':self.preflight(),'generated':False}
        from evolution_workers import bounded_fixture
        metadata=self.validate(self.path); pre=self.preflight()
        if not pre['eligible']: return {'status':'SKIPPED_RESOURCE_PREFLIGHT','preflight':pre,'generated':False}
        binary=Path.home()/'llama.cpp/build/bin/llama-cli'
        if not binary.is_file(): raise Denied('Existing llama-cli unavailable; no install/download')
        before=file_hash(self.path)
        result=bounded_fixture(self.arguments(binary,self.path,'Reply with exactly QWEN_FIXTURE_OK.'),self.path.parent,binary,wall=120,cpu=120,max_output=16384,env={k:v for k,v in os.environ.items() if k in {'HOME','PATH','PREFIX','TMPDIR','LANG','LD_LIBRARY_PATH'}},rss_limit_mib=1600,min_available_mib=768,available=memory_available_mib)
        result.update(preflight=pre,metadata=metadata,model_unchanged=file_hash(self.path)==before,generated=result['status']=='returned' and bool(result['stdout'].strip()),instruction_following=result['stdout'].strip()=='QWEN_FIXTURE_OK',attribution_validation='NOT_RUN')
        return result

class LoRARecipe:
    REQUIRED_GATES=('training_approved','weights_download_approved','gpu_provisioning_approved','personal_dataset_export_approved','model_promotion_approved')
    @classmethod
    def validate_disabled(cls,recipe):
        if recipe.get('enabled') is not False or any(recipe.get(k) is not False for k in cls.REQUIRED_GATES): raise Denied('Training/download/export/promotion must stay disabled')
        if recipe['base'].get('revision') is not None or recipe['runtime'].get('ready') is not False: raise Denied('Host/base not yet validated')
        return {'status':'DISABLED_PREPARATION_ONLY','run':False,'download':False,'base_candidate':recipe['base']['candidate_original']}
    @staticmethod
    def validate_base(base):
        if base.get('format')!='HF-original-FP' or base.get('id')!='Qwen/Qwen2.5-1.5B-Instruct' or not all(base.get(k) for k in ('revision','license_verified','tokenizer_hash','chat_template_hash')): raise Denied('Matching original FP revision/license/tokenizer/template required; GGUF is not a training base')
        return True
    @staticmethod
    def promotion(evaluation):
        required={'privacy_leaks':0,'source_attribution_regressions':0,'project_isolation_regressions':0,'conversion_failures':0}
        if any(evaluation.get(k)!=v for k,v in required.items()) or evaluation.get('quality_delta',-1)<-.02: raise Denied('Promotion blocked by evaluation')
        return {'eligible_for_human_review':True,'promoted':False}
    @staticmethod
    def version_paths(root,version):
        import re
        if not re.fullmatch('[A-Za-z0-9_-]{1,64}',version): raise Denied('Version required')
        target=Path(root)/version
        if target.exists(): raise Denied('Immutable version exists')
        return {'adapter':str(target/'adapter'),'merged_fp_copy':str(target/'merged-fp'),'f16':str(target/'model-f16.gguf'),'q4':str(target/'model-q4_k_m.gguf'),'original_unchanged':True}
