# Build: docker build -t edgechess-convert:py310 convert
# Run with convert mounted at /work/convert. GPU and privileged mode are not needed.
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3-pip ca-certificates libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
RUN python3.10 -m pip install --upgrade pip==25.0.1
RUN python3.10 -m pip install torch==2.4.0 --index-url https://download.pytorch.org/whl/cpu
COPY requirements-rknn.txt /tmp/requirements-rknn.txt
RUN python3.10 -m pip install -r /tmp/requirements-rknn.txt && python3.10 -m pip check
ENV OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
WORKDIR /work/convert
ENTRYPOINT ["python3.10"]
