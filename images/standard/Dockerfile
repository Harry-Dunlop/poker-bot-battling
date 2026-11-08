# bot-python-standard:3.12 — the Standard ladder sandbox image (design-doc §2, §4.1).
# The image is the library allow-list: nothing else can be installed at run time.
# Build on the runner VM:  docker build -t bot-python-standard:3.12 images/standard
FROM python:3.12-slim

# TODO(M4): pin exact versions once checked on the VM.
RUN pip install --no-cache-dir numpy scipy numba eval7 \
 && rm -rf /root/.cache

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMBA_NUM_THREADS=1 \
    NUMBA_CACHE_DIR=/tmp/numba

USER 65534:65534
WORKDIR /bot
CMD ["python", "-u", "/bot/main.py"]
