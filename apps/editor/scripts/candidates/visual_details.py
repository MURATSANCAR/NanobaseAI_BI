"""Blinded visual detail measurements; source pixels remain the only authority.

This does not read quotes, infer names or treat closed eyes as proof of sleep.
It records a separate observation and reviews an earlier candidate without
editing that candidate or promoting a caption into a textual source.
"""
import base64
import hashlib
import json

VERSION='source-visual-detail-review-v1'

def digest(raw):return hashlib.sha256(raw).hexdigest()

def review(crop, candidate, model):
    png=base64.b64decode(crop['image_base64'],validate=True)
    if digest(png)!=crop['crop_sha256']:
        raise RuntimeError('VISUAL_DETAIL_CROP_HASH_MISMATCH')
    image={'type':'image_url','image_url':{'url':'data:image/png;base64,'+crop['image_base64']}}
    prompt=('Yalnız bu figür kırpımının görülebilen ayrıntılarını ölç. Yazı okuma, isim veya konuşmacı tahmin etme. '
        'Gözlerin açık/kapalı çizilmesini uyku/uyanıklık veya duygu kanıtı sayma. İris/göz bebeği ile kapak çizgisini ayır; '
        'stilize, kesilmiş veya çözünürlüğü yetersiz ayrıntıda UNKNOWN kullan. Figür yoksa is_figure false. '
        'Önceki sayfa betimlemesi veya beklenen cevap verilmemiştir. '
        'JSON {"is_figure":true,"eyes":"OPEN|CLOSED|MIXED|NOT_VISIBLE|UNKNOWN",'
        '"eye_evidence":"yalnız görülen çizgi/biçim",'
        '"visible_posture":"LYING|SITTING|STANDING|OTHER|UNKNOWN",'
        '"posture_evidence":"yalnız görülen konum","uncertainties":["..."]}.')
    measured,metrics=model([{'role':'user','content':[{'type':'text','text':prompt},image]}],
                           max_tokens=700,prompt_version=VERSION+'-blind')
    result={'version':VERSION,'crop_sha256':crop['crop_sha256'],'crop_image_base64':crop['image_base64'],
        'candidate_sha256':digest(json.dumps(candidate,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()),
        'measurement':measured,'measurement_metrics':metrics,'original_candidate_modified':False,
        'candidate_supported':False,'eligible_for_synthesis':False,'semantic_acceptance':False,
        'sleep_state_inferred':False,'character_identity_inferred':False}
    if (not isinstance(measured,dict) or type(measured.get('is_figure')) is not bool
        or measured.get('eyes') not in ('OPEN','CLOSED','MIXED','NOT_VISIBLE','UNKNOWN')
        or measured.get('visible_posture') not in ('LYING','SITTING','STANDING','OTHER','UNKNOWN')
        or not all(isinstance(measured.get(k),str) and measured[k].strip() for k in ('eye_evidence','posture_evidence'))
        or not isinstance(measured.get('uncertainties'),list)
        or not all(isinstance(x,str) for x in measured['uncertainties'])):
        return {**result,'reason':'INVALID_VISUAL_DETAIL_MEASUREMENT'}
    if measured['is_figure'] is not True:
        return {**result,'reason':'FIGURE_NOT_VISIBLE_IN_CROP'}
    # The first call was blind to this candidate. The second sees the actual
    # same crop, not just either generated description as an alleged source.
    prompt=('Verilen önceki görsel adayı bu gerçek figür kırpımıyla denetle. Görsel aday ve ayrıntı ölçümü '
        'hipotezdir, kanıt değildir. Önceki adayı düzeltme; tüm iddiaları görülebiliyorsa supported true. '
        'Kesilmiş veya belirsiz ayrıntıyı destekleme. Kapalı gözden uyuyor, açık gözden bilinçli gibi durum çıkarma. '
        'İsim/alıntı/konuşmacı ve kaynakta görünmeyen eylem için ret ver. '
        'JSON {"supported":false,"reason":"kaynak ayrıntısıyla gerekçe",'
        '"contradictions":["..."],"uncertainties":["..."]}.\n'+
        json.dumps({'candidate':candidate,'blind_measurement':measured},ensure_ascii=False,separators=(',',':')))
    verdict,review_metrics=model([{'role':'user','content':[{'type':'text','text':prompt},image]}],
        max_tokens=700,prompt_version=VERSION+'-review')
    result.update(review=verdict,review_metrics=review_metrics,
                  review_method='SEPARATE_CALL_SAME_MODEL_ACTUAL_CROP_NOT_INDEPENDENT_EVIDENCE')
    valid=(isinstance(verdict,dict) and type(verdict.get('supported')) is bool
        and isinstance(verdict.get('reason'),str) and bool(verdict['reason'].strip())
        and all(isinstance(verdict.get(k),list) and all(isinstance(x,str) for x in verdict[k])
                for k in ('contradictions','uncertainties')))
    result['candidate_supported']=bool(valid and verdict['supported'] and not verdict['contradictions'] and not verdict['uncertainties'])
    result['reason']='VISUAL_CANDIDATE_SUPPORTED' if result['candidate_supported'] else 'VISUAL_CANDIDATE_REQUIRES_REVIEW'
    return result
