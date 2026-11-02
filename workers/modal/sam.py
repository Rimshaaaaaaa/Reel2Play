"""SAM 3.1 on a Modal GPU: text-prompted product masks for the cut-out step (feature 6), and
the same product followed across a short clip for animated sprites (feature 7).

Deploy:   modal deploy sam.py
Secrets:  a Modal secret named "huggingface" holding HF_TOKEN (accept the model's terms first)
Auth:     the endpoint needs a Modal proxy token: "Authorization: Bearer <id>.<secret>"
Model:    SAM_MODEL_ID below; unsloth/sam3.1 is the transformers-format copy of the SAM 3.1
          weights the build spec links (SAM License). facebook/sam3 is the official SAM 3.
"""

from __future__ import annotations

import os
from typing import Any

import modal

from sam_core import (
    FrameObjects,
    SegmentRequest,
    SegmentResponse,
    TrackRequest,
    TrackResponse,
    decode_image,
    to_response,
    track_response,
)

SAM_MODEL_ID = os.environ.get("SAM_MODEL_ID", "unsloth/sam3.1")

app = modal.App("reel2play-sam")
hf_cache = modal.Volume.from_name("huggingface-cache", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install(
        "torch>=2.8",
        "torchvision",
        "transformers>=5.14",
        "accelerate>=1.0",
        "fastapi[standard]>=0.115",
        "numpy>=2.1",
        "pillow>=11.0",
        "pydantic>=2.9",
    )
    .env({"HF_XET_HIGH_PERFORMANCE": "1", "SAM_MODEL_ID": SAM_MODEL_ID})
    .add_local_python_source("sam_core")
)


@app.cls(
    image=image,
    gpu="L4",
    volumes={"/root/.cache/huggingface": hf_cache},
    secrets=[modal.Secret.from_name("huggingface")],
    scaledown_window=300,
    timeout=600,
)
class Sam:
    @modal.enter()
    def load(self) -> None:
        import torch
        from transformers import Sam3Model, Sam3Processor

        self.torch = torch
        self.processor = Sam3Processor.from_pretrained(SAM_MODEL_ID)
        self.model = Sam3Model.from_pretrained(SAM_MODEL_ID, dtype=torch.bfloat16)
        self.model = self.model.to("cuda").eval()
        self.video_model: Any = None
        self.video_processor: Any = None

    def _video(self) -> tuple[Any, Any]:
        """The video model loads on the first tracking request, so cut-outs start faster."""
        if self.video_model is None:
            from transformers import Sam3VideoModel, Sam3VideoProcessor

            self.video_processor = Sam3VideoProcessor.from_pretrained(SAM_MODEL_ID)
            self.video_model = Sam3VideoModel.from_pretrained(SAM_MODEL_ID).to("cuda").eval()
        return self.video_model, self.video_processor

    @modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
    def segment(self, request: SegmentRequest) -> SegmentResponse:
        picture = decode_image(request.image)
        inputs: Any = self.processor(images=picture, text=request.prompt, return_tensors="pt")
        inputs = inputs.to("cuda", dtype=self.torch.bfloat16)
        with self.torch.no_grad():
            outputs = self.model(**inputs)
        result = self.processor.post_process_instance_segmentation(
            outputs,
            threshold=request.threshold,
            mask_threshold=request.mask_threshold,
            target_sizes=inputs.get("original_sizes").tolist(),
        )[0]
        return to_response(
            picture.width,
            picture.height,
            [m.cpu().numpy().astype(bool) for m in result["masks"]],
            result["boxes"].float().cpu().tolist(),
            result["scores"].float().cpu().tolist(),
            request.max_masks,
        )

    @modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
    def track(self, request: TrackRequest) -> TrackResponse:
        frames = [decode_image(f) for f in request.frames]
        size = frames[0].size
        frames = [f if f.size == size else f.resize(size) for f in frames]
        model, processor = self._video()
        session = processor.init_video_session(
            video=frames,
            inference_device="cuda",
            processing_device="cpu",
            video_storage_device="cpu",
        )
        session = processor.add_text_prompt(inference_session=session, text=request.prompt)
        found: dict[int, FrameObjects] = {}
        with self.torch.no_grad():
            for output in model.propagate_in_video_iterator(
                inference_session=session, max_frame_num_to_track=len(frames)
            ):
                result = processor.postprocess_outputs(session, output)
                found[int(output.frame_idx)] = FrameObjects(
                    ids=[int(i) for i in result["object_ids"].tolist()],
                    scores=[float(s) for s in result["scores"].float().cpu().tolist()],
                    masks=[m.cpu().numpy().astype(bool) for m in result["masks"]],
                )
        return track_response(
            size[0],
            size[1],
            found,
            len(frames),
            min(request.key_index, len(frames) - 1),
            request.box,
        )
