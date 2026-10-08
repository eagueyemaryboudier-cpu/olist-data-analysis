"""Télécharge uniquement les poids et fichiers de configuration, aucun code distant."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent / 'models' / 'sentiment'
REPO = 'onnx-community/twitter-xlm-roberta-base-sentiment-ONNX'


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    with urlopen(f'https://huggingface.co/api/models/{REPO}', timeout=60) as response:
        metadata = json.load(response)
    revision = metadata['sha']
    manifest = {'repository': REPO, 'revision': revision, 'files': {}}
    for name in ['config.json', 'tokenizer.json', 'tokenizer_config.json', 'onnx/model_quantized.onnx']:
        dest = ROOT / Path(name).name
        print('Téléchargement :', name, flush=True)
        digest = hashlib.sha256()
        with urlopen(f'https://huggingface.co/{REPO}/resolve/{revision}/{name}', timeout=120) as response, dest.with_suffix(dest.suffix + '.part').open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
        dest.with_suffix(dest.suffix + '.part').replace(dest)
        manifest['files'][dest.name] = {'sha256': digest.hexdigest(), 'bytes': dest.stat().st_size}
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Modèle local prêt.', flush=True)


if __name__ == '__main__':
    main()
