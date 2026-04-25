"""
AlertX | Violence & Scene Agent
Uses OpenAI's CLIP (Zero-Shot) to classify incidents and validate YOLO detections.
Inspired by https://github.com/sukhitashvili/violence-detection
"""

import torch
import clip
from PIL import Image
import cv2
import logging

logger = logging.getLogger("alertx.violence_agent")

class ViolenceAgent:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None
        self.preprocess = None
        self.labels = [
            "a photo of street violence or fighting",
            "a photo of a car accident or crash",
            "a photo of a fire or smoke",
            "a photo of a person with a gun or weapon",
            "a photo of a normal peaceful street",
            "a photo of a person walking normally"
        ]
        self._loaded = False

    def load(self):
        if self._loaded: return
        logger.info("Loading CLIP Violence Agent (ViT-B/32)...")
        self.model, self.preprocess = clip.load("ViT-B/32", device=self.device)
        self._loaded = True
        logger.info("CLIP Violence Agent loaded.")

    def process(self, data):
        """
        Validate YOLO detections using CLIP scene understanding.
        Input: data dict containing 'frame_result' (YOLOResult)
        """
        if not data or "frame_result" not in data:
            return data

        result = data["frame_result"]
        
        # Only run if YOLO detected something or if we want a random check
        if not result.incidents and not result.detections:
            return data

        if not self._loaded:
            self.load()

        # Get raw frame from result
        # Note: frame_result.annotated_frame is used here for context
        frame = result.annotated_frame
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        image_input = self.preprocess(image).unsqueeze(0).to(self.device)
        text_inputs = clip.tokenize(self.labels).to(self.device)

        with torch.no_grad():
            image_features = self.model.encode_image(image_input)
            text_features = self.model.encode_text(text_inputs)

            # Similarity
            logits_per_image, _ = self.model(image_input, text_inputs)
            probs = logits_per_image.softmax(dim=-1).cpu().numpy()[0]

        # Map results
        scores = {self.labels[i]: float(probs[i]) for i in range(len(self.labels))}
        
        # Logic: If violence/accident prob is high, boost severity
        violence_prob = scores["a photo of street violence or fighting"]
        accident_prob = scores["a photo of a car accident or crash"]
        fire_prob = scores["a photo of a fire or smoke"]

        if violence_prob > 0.4:
            logger.warning(f"CLIP confirmed VIOLENCE with {violence_prob:.2f} confidence")
            # Inject into incidents if not there
            if not any(i["type"] == "fight" for i in result.incidents):
                result.incidents.append({"type": "fight", "confidence": violence_prob, "class_name": "clip_validation"})
            data["high_priority_summary"] = "Confirmed physical altercation detected via secondary AI analysis."

        if fire_prob > 0.6:
             logger.warning(f"CLIP confirmed FIRE with {fire_prob:.2f} confidence")
             if not any(i["type"] == "fire" for i in result.incidents):
                result.incidents.append({"type": "fire", "confidence": fire_prob, "class_name": "clip_validation"})

        return data

    @property
    def stats(self):
        return {"model": "CLIP ViT-B/32", "status": "active" if self._loaded else "standby"}
