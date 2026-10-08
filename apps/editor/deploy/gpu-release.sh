# GPU editör sürüm kurulumu (tt-gpu'da koşar): main'in tamamı tek sürüm klasörü + tek imaj.
# Kullanım: önce `git archive origin/main apps/editor` → /data/editor/releases/<sha8> (Mac artığı yok), sonra
#   setsid nohup bash gpu-release.sh <sha8> > /tmp/editor-deploy-<sha8>.log 2>&1 &
# Okuma servisleri (worker rebuild book-queue) yeniden yaratılmaz: süren kitap okumalarını keser (21:00 sonrası kur).
set -euo pipefail
SHA=${1:?sha8 gerekli}
REL=/data/editor/releases/$SHA; VER=0.15.9-$SHA
echo "$VER" > $REL/VERSION
find $REL -name '._*' -type f -delete
docker build -q -t editor-py:$VER --build-arg CODE_VERSION=$VER -f $REL/images/py/Dockerfile $REL
docker build -q -t editor-py-studio:$VER --build-arg BASE=editor-py:$VER -f $REL/images/studio/Dockerfile $REL/images/studio
echo "== testler"
# images/ şart: tests/test_film.py images/video/plan.py'yi yükler (imaj images/ taşımaz)
docker run --rm -v $REL/tests:/app/tests -v $REL/connectors:/app/connectors -v $REL/deploy:/app/deploy \
  -v $REL/images:/app/images -w /app -e PYTHONPATH=/app/src:/app/connectors editor-py-studio:$VER \
  sh -c "pip install -q pytest >/dev/null 2>&1; python -m pytest -q -p no:cacheprovider tests/ 2>&1 | tail -3" </dev/null
ln -sfn $REL /data/editor/app
echo "== servisler (okuma servisleri durdurulmuş kalır: worker rebuild book-queue yok)"
cd $REL
sudo env EDITOR_ROOT=/data/editor EDITOR_PY_IMAGE=editor-py:$VER EDITOR_CARDS_IMAGE=editor-py:$VER \
  EDITOR_STUDIO_IMAGE=editor-py-studio:$VER docker compose -f deploy/docker-compose.yml --project-name editor \
  --profile analysis up -d --no-deps cards control studio studio-worker gateway document-review </dev/null
sleep 20
echo "== sürümler"
for c in editor-gateway editor-cards editor-studio editor-studio-worker editor-control editor-document-review; do
  printf '%s %s\n' "$c" "$(docker exec $c sh -c 'echo $EDITOR_CODE_VERSION' </dev/null 2>/dev/null || echo yok)"
done
echo "Mac artığı: $(find $REL -name '._*' | wc -l)"
docker ps --format '{{.Names}} {{.Status}}' | grep editor- | sort
echo TAMAM
