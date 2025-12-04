# TensorBoard Server

Standalone TensorBoard server for ClaimHawk trainers.

Provides two independent TensorBoard endpoints:
- `tensorboard_lora`: For lora-trainer runs (`/volume/tensorboard`)
- `tensorboard_router`: For mole-trainer-server/router runs (`/moe-data/tb_logs`)

These run separately from training, so starting/stopping training does not affect TensorBoard availability.

## Usage

```bash
# Deploy both endpoints (recommended - keeps URLs stable)
modal deploy modal/tb_server.py

# Or run temporarily
modal serve modal/tb_server.py
```

Access via the Modal dashboard URLs or:
- `https://<your-workspace>--tensorboard-server-tensorboard-lora.modal.run`
- `https://<your-workspace>--tensorboard-server-tensorboard-router.modal.run`

## Cleanup Tool

Interactive cleanup of old TensorBoard logs:

```bash
# Clean up lora-trainer logs
modal run scripts/cleanup.py --trainer lora

# Clean up router trainer logs
modal run scripts/cleanup.py --trainer router

# Clean up both
modal run scripts/cleanup.py --trainer all
```
