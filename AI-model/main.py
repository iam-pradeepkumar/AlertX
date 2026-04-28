import cv2
import numpy as np
from ultralytics import YOLO
from tensorflow.keras.models import load_model
from collections import deque

# -------------------------------
# LOAD MODELS
# -------------------------------
object_model = YOLO("yolov8n.pt")   # fast

try:
    weapon_model = YOLO("best.pt")
    weapon_ok = True
except:
    weapon_ok = False

fight_model = load_model("fightdetection.h5", compile=False)

# -------------------------------
# SETTINGS
# -------------------------------
IMG_SIZE = 128
VIOLENCE_THRESHOLD = 0.6

pred_buffer = deque(maxlen=10)

# -------------------------------
# PREPROCESS
# -------------------------------
def preprocess(frame):
    img = cv2.resize(frame, (IMG_SIZE, IMG_SIZE))
    img = img / 255.0
    return np.reshape(img, (1, IMG_SIZE, IMG_SIZE, 3))

# -------------------------------
# VIDEO
# -------------------------------
cap = cv2.VideoCapture(0)

frame_count = 0
last_boxes = []
last_event = "SAFE"
last_weapon = False
person_count = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # 🔥 Bigger screen
    frame = cv2.resize(frame, (800, 600))
    small = cv2.resize(frame, (320, 320))

    frame_count += 1

    # -------------------------------
    # ROTATING MODEL EXECUTION
    # -------------------------------

    # 1️⃣ OBJECT DETECTION
    if frame_count % 3 == 0:
        results = object_model(small, verbose=False)

        new_boxes = []
        person_count = 0

        for r in results:
            for box in r.boxes:
                if float(box.conf[0]) < 0.5:
                    continue

                label = object_model.names[int(box.cls[0])]
                x1, y1, x2, y2 = map(int, box.xyxy[0])

                # scale
                x1 = int(x1 * 800 / 320)
                x2 = int(x2 * 800 / 320)
                y1 = int(y1 * 600 / 320)
                y2 = int(y2 * 600 / 320)

                new_boxes.append((x1, y1, x2, y2, label))

                if label == "person":
                    person_count += 1

        if new_boxes:
            last_boxes = new_boxes

    # 2️⃣ WEAPON DETECTION (HIGH PRIORITY)
    if weapon_ok and frame_count % 3 == 1:
        last_weapon = False

        results = weapon_model(small, verbose=False)

        for r in results:
            for box in r.boxes:
                if float(box.conf[0]) > 0.5:
                    last_weapon = True

    # 3️⃣ VIOLENCE DETECTION
    if frame_count % 3 == 2:
        for (x1, y1, x2, y2, label) in last_boxes:
            if label == "person":
                crop = frame[y1:y2, x1:x2]

                if crop.size == 0:
                    continue

                pred = float(fight_model.predict(
                    preprocess(crop), verbose=0
                )[0][0])

                pred_buffer.append(pred)

    # -------------------------------
    # DECISION (STABLE)
    # -------------------------------
    violence_flag = False

    if len(pred_buffer) > 0:
        if sum(pred_buffer)/len(pred_buffer) > VIOLENCE_THRESHOLD and person_count >= 2:
            violence_flag = True

    # PRIORITY ORDER
    if last_weapon:
        last_event = "WEAPON 🔫"

    elif violence_flag:
        last_event = "VIOLENCE 🚨"

    elif person_count >= 4:
        last_event = "CROWD ⚠️"

    else:
        last_event = "SAFE"

    # -------------------------------
    # DRAW
    # -------------------------------
    for (x1, y1, x2, y2, label) in last_boxes:
        color = (0,0,255) if last_event != "SAFE" else (0,255,0)

        cv2.rectangle(frame, (x1,y1),(x2,y2), color, 2)
        cv2.putText(frame, label, (x1, y1-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    # BIG ALERT TEXT
    cv2.putText(frame, last_event, (20,60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5,
                (0,0,255) if last_event != "SAFE" else (0,255,0), 4)

    cv2.putText(frame, f"People: {person_count}", (20,100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,0), 2)

    cv2.imshow("SMART AI SYSTEM", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
