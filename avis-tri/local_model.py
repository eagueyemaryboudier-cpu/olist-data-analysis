"""Inférence ONNX hors ligne, sans exécution de code provenant du modèle."""
import json
import os
import re
import sys
import threading
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.runtime'))
MODEL = ROOT / 'models' / 'sentiment'
_engine = None
_lock = threading.Lock()


def available():
    return all((MODEL / name).is_file() for name in ['tokenizer.json', 'config.json', 'model_quantized.onnx', 'manifest.json'])


class Engine:
    def __init__(self):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np = np
        options = ort.SessionOptions()
        options.intra_op_num_threads = min(4, os.cpu_count() or 2)
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(MODEL / 'model_quantized.onnx'), sess_options=options, providers=['CPUExecutionProvider'])
        self.tokenizer = Tokenizer.from_file(str(MODEL / 'tokenizer.json'))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        self.labels = json.loads((MODEL / 'config.json').read_text())['id2label']
        self.cache = OrderedDict()

    def predict(self, texts):
        np = self.np
        missing = list(dict.fromkeys(t for t in texts if t not in self.cache))
        chunks, owners, weights = [], [], []
        for text in missing:
            if len(text) > 100_000:
                raise ValueError('Un commentaire dépasse 100 000 caractères. Scinde ce document en avis.')
            clean = re.sub(r'https?://\S+', 'http', text)
            clean = re.sub(r'(?<!\w)@\w+', '@user', clean)
            # Découpage explicite : ne pas dépendre des overflow tokens du tokenizer.
            tokens = self.tokenizer.encode(clean, add_special_tokens=False).ids
            parts = [tokens[i:i+254] for i in range(0, len(tokens), 254)] or [[]]
            for part in parts:
                chunks.append([0, *part, 2])
                owners.append(text)
                weights.append(max(1, len(part)))
        sums = {t: np.zeros(3) for t in missing}
        totals = {t: 0 for t in missing}
        extremes = {t: set() for t in missing}
        for offset in range(0, len(chunks), 8):
            batch = chunks[offset:offset+8]
            width = max(len(e) for e in batch)
            ids = np.array([e + [1]*(width-len(e)) for e in batch], dtype=np.int64)
            mask = np.array([[1]*len(e) + [0]*(width-len(e)) for e in batch], dtype=np.int64)
            feed = {'input_ids': ids, 'attention_mask': mask}
            inputs = {x.name: feed.get(x.name, np.zeros_like(ids)) for x in self.session.get_inputs()}
            logits = self.session.run(None, inputs)[0]
            scores = np.exp(logits - logits.max(axis=1, keepdims=True))
            scores /= scores.sum(axis=1, keepdims=True)
            for k, score in enumerate(scores):
                text, weight = owners[offset+k], weights[offset+k]
                sums[text] += score * weight
                totals[text] += weight
                best = int(score.argmax())
                ordered = np.sort(score)
                if score[best] >= .60 and ordered[-1] - ordered[-2] >= .15:
                    extremes[text].add(self.labels[str(best)].lower())
        labels_fr = {'positive': 'Positif', 'negative': 'Négatif', 'neutral': 'Neutre'}
        for text in missing:
            scores = sums[text] / totals[text]
            rank = np.argsort(scores)[::-1]
            best, runner = int(rank[0]), int(rank[1])
            score, margin = float(scores[best]), float(scores[best]-scores[runner])
            uncertain = score < .60 or margin < .15
            label = labels_fr[self.labels[str(best)].lower()]
            if {'positive', 'negative'} <= extremes[text]:
                label, uncertain = 'Mixte', True
            elif uncertain:
                label = 'Indéterminé'
            self.cache[text] = {'sentiment': label, 'confidence': round(score, 4), 'uncertain': uncertain,
                                'probabilities': {labels_fr[self.labels[str(i)].lower()]: round(float(p),4) for i,p in enumerate(scores)},
                                'chunks': owners.count(text)}
        answer = [dict(self.cache[t]) for t in texts]
        while len(self.cache) > 50_000:
            self.cache.popitem(last=False)
        return answer


def predict(texts):
    global _engine
    with _lock:
        if not available():
            raise ValueError('Modèle absent : exécute python download_model.py avant l’analyse locale.')
        if _engine is None:
            _engine = Engine()
        return _engine.predict(texts)
