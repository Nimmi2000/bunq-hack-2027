"""
AWS Rekognition face operations: enroll, compare, and quality check.

Enrollment stores only an opaque FaceId (no raw image) in enrolled_faces.json.
Collection: configured via REKOGNITION_COLLECTION_ID env var (default: bunq-faces).
"""

import json
import os

import boto3

AWS_REGION = os.environ.get("AWS_REGION", "eu-west-1")
COLLECTION_ID = os.environ.get("REKOGNITION_COLLECTION_ID", "bunq-faces")
ENROLLED_FILE = os.path.join(os.path.dirname(__file__), "..", "enrolled_faces.json")

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("rekognition", region_name=AWS_REGION)
    return _client


def load_enrolled() -> dict:
    try:
        with open(ENROLLED_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_enrolled(data: dict) -> None:
    with open(ENROLLED_FILE, "w") as f:
        json.dump(data, f, indent=2)


def ensure_collection() -> None:
    client = _get_client()
    try:
        client.create_collection(CollectionId=COLLECTION_ID)
    except client.exceptions.ResourceAlreadyExistsException:
        pass


def enroll_face(user_id: str, image_bytes: bytes) -> dict:
    """Index a face into Rekognition and save FaceId locally. Returns enrollment info."""
    ensure_collection()
    client = _get_client()

    response = client.index_faces(
        CollectionId=COLLECTION_ID,
        Image={"Bytes": image_bytes},
        ExternalImageId=user_id,
        MaxFaces=1,
        QualityFilter="AUTO",
        DetectionAttributes=[],
    )

    faces = response.get("FaceRecords", [])
    if not faces:
        raise ValueError("No face detected in the enrollment image.")

    face_id = faces[0]["Face"]["FaceId"]

    enrolled = load_enrolled()
    # Merge into existing record so enrolled_image_b64 (saved by setup_enrollment.py) is preserved
    record = enrolled.get(user_id, {})
    record.update({"face_id": face_id, "collection_id": COLLECTION_ID, "method": "rekognition+local"})
    enrolled[user_id] = record
    _save_enrolled(enrolled)

    return {"user_id": user_id, "face_id": face_id, "collection_id": COLLECTION_ID}


def compare_face(image_bytes: bytes, user_id: str = "eva") -> dict:
    """Search for user_id's face in the Rekognition collection. Returns match info."""
    enrolled = load_enrolled()
    if user_id not in enrolled:
        return {"matched": False, "similarity": 0.0, "error": f"User '{user_id}' not enrolled"}
    # If face was enrolled locally (no Rekognition index), force Claude Vision fallback
    if not enrolled[user_id].get("face_id"):
        return {"matched": False, "similarity": 0.0, "error": "Not indexed in Rekognition — using Claude Vision fallback"}

    client = _get_client()

    try:
        response = client.search_faces_by_image(
            CollectionId=COLLECTION_ID,
            Image={"Bytes": image_bytes},
            MaxFaces=1,
            FaceMatchThreshold=70,
        )
        matches = response.get("FaceMatches", [])
        if not matches:
            return {"matched": False, "similarity": 0.0}

        top = matches[0]
        similarity = top.get("Similarity", 0.0)
        matched_face_id = top.get("Face", {}).get("FaceId", "")
        enrolled_face_id = enrolled[user_id]["face_id"]

        return {
            "matched": matched_face_id == enrolled_face_id and similarity >= 70,
            "similarity": round(similarity, 1),
            "face_id": matched_face_id,
        }

    except client.exceptions.InvalidParameterException:
        return {"matched": False, "similarity": 0.0, "error": "No face detected in image"}
    except Exception as exc:
        return {"matched": False, "similarity": 0.0, "error": str(exc)}


def get_face_quality(image_bytes: bytes) -> dict:
    """Detect face quality signals (sharpness, brightness). Returns quality info."""
    client = _get_client()

    try:
        response = client.detect_faces(
            Image={"Bytes": image_bytes},
            Attributes=["QUALITY"],
        )
        faces = response.get("FaceDetails", [])
        if not faces:
            return {"quality_ok": False, "sharpness": 0.0, "brightness": 0.0, "face_count": 0}

        quality = faces[0].get("Quality", {})
        sharpness = quality.get("Sharpness", 0.0)
        brightness = quality.get("Brightness", 0.0)

        return {
            "quality_ok": sharpness > 20 and brightness > 20,
            "sharpness": round(sharpness, 1),
            "brightness": round(brightness, 1),
            "face_count": len(faces),
        }

    except Exception as exc:
        return {"quality_ok": True, "sharpness": 0.0, "brightness": 0.0, "error": str(exc)}
