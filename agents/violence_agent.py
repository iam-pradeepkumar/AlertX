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
            "a photo of a person falling down or a medical emergency",
            "a photo of a person running away fast in panic",
            "a photo of a person breaking a window or glass",
            "a photo of a person climbing a fence or wall",
            "a photo of a person hiding their face or wearing a mask",
            "a photo of a normal peaceful scene"
        ]
        self._loaded = False

    def load(self):
        if self._loaded: return
        logger.info("Loading CLIP Activity Agent (ViT-B/32)...")
        self.model, self.preprocess = clip.load("ViT-B/32", device=self.device)
        self._loaded = True
        logger.info("CLIP Activity Agent loaded.")

    def process(self, data):
        """
        Detect complex activities and suspicious behaviors.
        """
        if not data or "frame_result" not in data:
            return data

        result = data["frame_result"]
        
        # We run this even if YOLO sees nothing (to catch fire/smoke etc)
        if not self._loaded:
            self.load()

        frame = result.raw_frame if result.raw_frame is not None else result.annotated_frame
        if frame is None: return data
        
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        image_input = self.preprocess(image).unsqueeze(0).to(self.device)
        text_inputs = clip.tokenize(self.labels).to(self.device)

        with torch.no_grad():
            logits_per_image, _ = self.model(image_input, text_inputs)
            probs = logits_per_image.softmax(dim=-1).cpu().numpy()[0]

        # Map results
        scores = {self.labels[i]: float(probs[i]) for i in range(len(self.labels))}
        
        # ACTIVITY LOGIC (Triggering Alerts)
        active_incidents = []

        # 1. High Priority (Violence/Accident/Fire)
        if scores["a photo of street violence or fighting"] > 0.65:
            active_incidents.append({
                "type": "fight", 
                "confidence": scores["a photo of street violence or fighting"],
                "severity_score": 0.95 # CRITICAL
            })
        
        if scores["a photo of a fire or smoke"] > 0.75:
            active_incidents.append({
                "type": "fire", 
                "confidence": scores["a photo of a fire or smoke"],
                "severity_score": 0.99 # CRITICAL
            })

        if scores["a photo of a car accident or crash"] > 0.70:
            active_incidents.append({
                "type": "accident", 
                "confidence": scores["a photo of a car accident or crash"],
                "severity_score": 0.90 # CRITICAL
            })

        # 2. Medium Priority (Suspicious/Medical)
        if scores["a photo of a person falling down or a medical emergency"] > 0.60:
            active_incidents.append({
                "type": "medical", 
                "confidence": scores["a photo of a person falling down or a medical emergency"],
                "severity_score": 0.75 # HIGH
            })

        if scores["a photo of a person breaking a window or glass"] > 0.55:
            active_incidents.append({
                "type": "vandalism", 
                "confidence": scores["a photo of a person breaking a window or glass"],
                "severity_score": 0.85 # HIGH
            })

        if scores["a photo of a person climbing a fence or wall"] > 0.65:
            active_incidents.append({
                "type": "suspicious", 
                "confidence": scores["a photo of a person climbing a fence or wall"],
                "severity_score": 0.60 # MEDIUM
            })

        if scores["a photo of a person hiding their face or wearing a mask"] > 0.70:
            active_incidents.append({
                "type": "suspicious", 
                "confidence": scores["a photo of a person hiding their face or wearing a mask"],
                "severity_score": 0.70 # MEDIUM
            })

        # Inject detected activities into the frame result
        for inc in active_incidents:
            if not any(existing["type"] == inc["type"] for existing in result.incidents):
                result.incidents.append(inc)
                logger.warning(f"CLIP Activity Detected: {inc['type']} ({inc['confidence']:.2f})")
                data["high_priority_summary"] = f"Activity detected: {inc['type'].upper()} confirmed via CLIP."

        return data

    @property
    def stats(self):
        return {"model": "CLIP ViT-B/32", "status": "active" if self._loaded else "standby"}
