#!/usr/bin/env python
"""
One-time face enrollment for Finn fraud detection.

Usage:
  python setup_enrollment.py --image /path/to/photo.jpg --user eva
  python setup_enrollment.py --webcam --user eva

Saves the reference photo as base64 in enrolled_faces.json so that
Claude Vision can compare live frames against it during transactions.
AWS Rekognition is attempted as an optional extra (requires IAM credentials)
but is NOT required — the system works without it.
"""

import argparse
import base64
import json
import os
import sys

from dotenv import load_dotenv
load_dotenv()

ENROLLED_FILE = os.path.join(os.path.dirname(__file__), "enrolled_faces.json")


def _load_enrolled() -> dict:
    try:
        with open(ENROLLED_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_enrolled(data: dict) -> None:
    with open(ENROLLED_FILE, "w") as f:
        json.dump(data, f, indent=2)


def enroll_from_file(image_path: str, user_id: str) -> None:
    if not os.path.exists(image_path):
        print(f"Error: image file not found: {image_path}")
        sys.exit(1)

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    _enroll(user_id, image_bytes, source=image_path)


def enroll_from_webcam(user_id: str) -> None:
    try:
        import cv2
    except ImportError:
        print("opencv-python is required for webcam mode.")
        sys.exit(1)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: cannot open webcam.")
        sys.exit(1)

    print("Webcam enrollment — position your face, then press SPACE to capture (Q to quit).")
    captured = False
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        cv2.putText(frame, "SPACE = capture | Q = quit", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 0), 2)
        cv2.imshow("Finn Enrollment", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            print("Cancelled.")
            break
        elif key == ord(" "):
            _, buf = cv2.imencode(".jpg", frame)
            cap.release()
            cv2.destroyAllWindows()
            _enroll(user_id, buf.tobytes(), source="webcam")
            captured = True
            break

    if not captured:
        cap.release()
        cv2.destroyAllWindows()


def _enroll(user_id: str, image_bytes: bytes, source: str) -> None:
    print(f"Enrolling '{user_id}' from {source} …")

    record: dict = {
        "user_id": user_id,
        "enrolled_image_b64": base64.b64encode(image_bytes).decode(),
        "face_id": None,
        "collection_id": None,
        "method": "local",
    }

    # Try Rekognition — optional, requires AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY
    try:
        from detection.rekognition import enroll_face
        result = enroll_face(user_id, image_bytes)
        record["face_id"] = result["face_id"]
        record["collection_id"] = result["collection_id"]
        record["method"] = "rekognition+local"
        print(f"  Rekognition face indexed: {result['face_id']}")
    except Exception as e:
        print(f"  Rekognition skipped ({type(e).__name__}) — using Claude Vision comparison instead.")

    enrolled = _load_enrolled()
    enrolled[user_id] = record
    _save_enrolled(enrolled)

    print(f"  Saved to enrolled_faces.json")
    print(f"  Method : {record['method']}")
    print(f"  Done! Run the app with: python -m uv run streamlit run app.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enroll a face for Finn fraud detection.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", metavar="PATH", help="Path to a JPEG or PNG photo")
    source.add_argument("--webcam", action="store_true", help="Capture live from webcam")
    parser.add_argument("--user", default="eva", help="User ID to enroll (default: eva)")

    args = parser.parse_args()
    if args.image:
        enroll_from_file(args.image, args.user)
    else:
        enroll_from_webcam(args.user)
