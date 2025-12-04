# Copyright 2025 Tylt, Inc.
# SPDX-License-Identifier: MIT
"""
Standalone TensorBoard Server for ClaimHawk Training

Provides two independent TensorBoard endpoints:
- tensorboard_lora: For lora-trainer runs (/volume/tensorboard)
- tensorboard_router: For mole-trainer-server/router runs (/moe-data/tb_logs)

These run separately from training, so starting/stopping training
does not affect TensorBoard availability.

Usage:
    # Deploy both endpoints (recommended - keeps URLs stable)
    modal deploy modal/tensorboard.py

    # Or run temporarily
    modal serve modal/tensorboard.py

    # Access via the Modal dashboard URLs or:
    # https://<your-workspace>--tensorboard-server-tensorboard-lora.modal.run
    # https://<your-workspace>--tensorboard-server-tensorboard-router.modal.run
"""

import modal

app = modal.App("tensorboard-server")

# Reference the volumes from the trainers (read-only access is fine)
lora_volume = modal.Volume.from_name("claimhawk-lora-training", create_if_missing=False)
moe_volume = modal.Volume.from_name("moe-lora-data", create_if_missing=False)

# Minimal image with just TensorBoard
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("tensorboard>=2.14.0")
)


@app.function(
    image=image,
    volumes={"/volume": lora_volume},
)
@modal.web_server(6006, startup_timeout=60)
def tensorboard_lora():
    """
    TensorBoard for LoRA trainer runs.

    Serves logs from /volume/tensorboard/{dataset_name}/{run_name}/
    """
    import subprocess

    subprocess.Popen([
        "tensorboard",
        "--logdir=/volume/tensorboard",
        "--host=0.0.0.0",
        "--port=6006",
        "--reload_interval=30",
    ])


@app.function(
    image=image,
    volumes={"/moe-data": moe_volume},
)
@modal.web_server(6007, startup_timeout=60)
def tensorboard_router():
    """
    TensorBoard for MoE router trainer runs.

    Serves logs from /moe-data/tb_logs/{dataset_name}/{run_name}/
    """
    import subprocess

    subprocess.Popen([
        "tensorboard",
        "--logdir=/moe-data/tb_logs",
        "--host=0.0.0.0",
        "--port=6007",
        "--reload_interval=30",
    ])
