"""Numeric model timings only; never forward model text or arbitrary metadata."""
import math

def model_timings(frame):
    result={}
    for source,target in (('load_duration','load'),('prompt_eval_duration','prompt'),('eval_duration','eval')):
        value=frame.get(source)
        if isinstance(value,(int,float)) and not isinstance(value,bool) and 0<=value<=3_600_000_000_000 and math.isfinite(value):
            result[target]=value/1_000_000
    return result
