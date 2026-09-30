#!/bin/bash

ENV_NAME="edgechess"

conda create -n $ENV_NAME python=3.10 -y
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate $ENV_NAME

pip install --upgrade pip

# PyTorch + CUDA
pip install torch torchvision torchaudio

# YOLO
pip install ultralytics

# Computer Vision
pip install opencv-python

# Изображения и визуализация
pip install numpy matplotlib pillow

# Утилиты
pip install pyyaml tqdm

echo ""
echo "Environment '$ENV_NAME' created!"
echo "Activate with: conda activate $ENV_NAME"