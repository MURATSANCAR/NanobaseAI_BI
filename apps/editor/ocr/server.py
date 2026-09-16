"""Private, serial CPU OCR service. Exact recognized text and polygon evidence only."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import time
from threading import BoundedSemaphore

import numpy as np
import cv2
from PIL import Image
from paddleocr import PaddleOCR, TextRecognition

ocr = PaddleOCR(text_detection_model_name='PP-OCRv5_mobile_det',
    text_detection_model_dir='/opt/models/PP-OCRv5_mobile_det',
    text_recognition_model_name='latin_PP-OCRv5_mobile_rec',
    text_recognition_model_dir='/opt/models/latin_PP-OCRv5_mobile_rec',
    use_doc_orientation_classify=False, use_doc_unwarping=False,
    use_textline_orientation=False, device='cpu', cpu_threads=4,
    enable_mkldnn=False)
region_reader = TextRecognition(model_name='latin_PP-OCRv5_mobile_rec',
    model_dir='/opt/models/latin_PP-OCRv5_mobile_rec', device='cpu',
    cpu_threads=4, enable_mkldnn=False)
manifest = json.loads(Path('/opt/models/manifest.json').read_text())
inference_slot = BoundedSemaphore(1)

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.reply(200 if self.path == '/health' else 404,
                   {'ready': True, 'models': manifest} if self.path == '/health' else {})

    def do_POST(self):
        if self.path not in ('/ocr', '/crop'):
            return self.reply(404, {})
        if not inference_slot.acquire(blocking=False):
            return self.reply(429, {'error': 'OCR_BUSY'})
        try:
            self.recognize()
        finally:
            inference_slot.release()

    def recognize(self):
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self.reply(400, {'error': 'INVALID_LENGTH'})
        if not 0 < size <= 16 * 1024 * 1024:
            return self.reply(413, {'error': 'IMAGE_SIZE_LIMIT'})
        try:
            body = json.loads(self.rfile.read(size))
            raw = base64.b64decode(body['image_base64'], validate=True)
            image = Image.open(io.BytesIO(raw))
            if image.width * image.height > 20_000_000:
                return self.reply(413, {'error': 'PIXEL_LIMIT'})
            pixels = np.asarray(image.convert('RGB'))[:, :, ::-1].copy()
        except (ValueError, KeyError, OSError):
            return self.reply(400, {'error': 'INVALID_IMAGE'})
        started = time.monotonic()
        try:
            if self.path == '/crop':
                box = body.get('bbox')
                if not isinstance(box, list) or len(box)!=4 or any(not isinstance(v,(int,float)) for v in box):
                    return self.reply(400, {'error':'INVALID_BBOX'})
                x,y,w,h=box
                if min(x,y)<0 or min(w,h)<=0 or x+w>1.001 or y+h>1.001:
                    return self.reply(400, {'error':'INVALID_BBOX'})
                crop=image.crop((int(x*image.width),int(y*image.height),
                                 min(image.width,int((x+w)*image.width)),min(image.height,int((y+h)*image.height))))
                stream=io.BytesIO(); crop.save(stream,format='PNG'); cropped=stream.getvalue()
                return self.reply(200, {'image_base64':base64.b64encode(cropped).decode(),
                    'crop_sha256':hashlib.sha256(cropped).hexdigest(),
                    'source_image_sha256':hashlib.sha256(raw).hexdigest(),'bbox':box})
            result = list(ocr.predict(pixels))[0]
            lines = [{'text': t, 'score': float(s), 'polygon': p.tolist()}
                     for t, s, p in zip(result['rec_texts'], result['rec_scores'], result['rec_polys'])]
            # Geometry candidates only: white closed regions containing detected text.
            # White shapes/backgrounds are not automatically speech balloons.
            white=(np.min(pixels,axis=2)>230).astype(np.uint8)*255
            contours,_=cv2.findContours(white,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            balloons=[]
            for contour in contours:
                area=cv2.contourArea(contour)/(image.width*image.height)
                if not .002<area<.35: continue
                x,y,w,h=cv2.boundingRect(contour)
                if x<=1 or y<=1 or x+w>=image.width-1 or y+h>=image.height-1: continue
                inside=[]
                for idx,line in enumerate(lines):
                    center=np.asarray(line['polygon']).mean(axis=0)
                    if cv2.pointPolygonTest(contour,tuple(map(float,center)),False)>=0: inside.append(idx)
                if not inside: continue
                polygon=cv2.approxPolyDP(contour,.008*cv2.arcLength(contour,True),True).reshape(-1,2)
                tips=[]
                if len(polygon)>=3:
                    for idx,point in enumerate(polygon):
                        a=polygon[idx-1].astype(float)-point; b=polygon[(idx+1)%len(polygon)].astype(float)-point
                        angle=np.degrees(np.arccos(np.clip(np.dot(a,b)/max(1e-9,np.linalg.norm(a)*np.linalg.norm(b)),-1,1)))
                        if angle<55: tips.append([float(point[0])/image.width,float(point[1])/image.height])
                balloons.append({'bbox':[x/image.width,y/image.height,w/image.width,h/image.height],
                    'text_line_indices':inside,'tail_tip_candidates':tips,
                    'status':'GEOMETRY_CANDIDATE','speaker':'UNKNOWN'})
            # Re-read automatically detected text regions; never accept supplied answers.
            regional = bool(body.get('regional_pass', False))
            if regional:
                for line in lines[:128]:
                    polygon = np.asarray(line['polygon'])
                    x0, y0 = np.maximum(polygon.min(axis=0).astype(int)-[4, 2], 0)
                    x1, y1 = np.minimum(polygon.max(axis=0).astype(int)+[4, 2],
                                        [image.width, image.height])
                    crop = image.crop((int(x0), int(y0), int(x1), int(y1)))
                    crop = crop.resize((crop.width*2, crop.height*2))
                    reread = list(region_reader.predict(np.asarray(crop.convert('RGB'))[:, :, ::-1].copy()))[0]
                    line['region_text'] = reread['rec_text']
                    line['region_score'] = float(reread['rec_score'])
                    line['region_box'] = [int(x0), int(y0), int(x1), int(y1)]
                    line['reading_agrees'] = ' '.join(line['text'].split()) == ' '.join(line['region_text'].split())
                    line['status'] = 'CONSISTENT_CANDIDATE' if line['reading_agrees'] else 'NEEDS_REVIEW'
            self.reply(200, {'image_sha256': hashlib.sha256(raw).hexdigest(),
                'width': image.width, 'height': image.height, 'lines': lines,
                'balloon_candidates':balloons[:128], 'balloons_truncated':len(balloons)>128,
                'reader_policy':'direct-line-reread-v2-128',
                'seconds': round(time.monotonic()-started, 3), 'models': manifest,
                'regional_pass': regional, 'regional_limit': 128,
                'regional_truncated': regional and len(lines) > 128,
                'status': 'CANDIDATE', 'engine': 'paddleocr-3.2.0/paddlepaddle-3.2.0'})
        except Exception as exc:
            print(type(exc).__name__, flush=True)
            self.reply(500, {'error': 'OCR_FAILED'})

ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
