import os
import cv2
import requests
import logging
import tempfile
from typing import Optional

logger = logging.getLogger("alertx.image_host")

def upload_frame(frame) -> Optional[str]:
    """
    Tries multiple anonymous hosting services with fallbacks to ensure 
    the screenshot is always delivered to WhatsApp.
    """
    tmp_path = None
    try:
        # Create a temp JPG file
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
            cv2.imwrite(tmp_path, frame)

        # Common headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        # --- SERVICE 1: Imgur (BEST: Trusted by Twilio) ---
        try:
            with open(tmp_path, 'rb') as f:
                # Using a generic public Client-ID
                img_headers = {**headers, 'Authorization': 'Client-ID 54443534700a1e2'}
                r = requests.post('https://api.imgur.com/3/image', files={'image': f}, headers=img_headers, timeout=12)
                if r.status_code == 200:
                    url = r.json().get('data', {}).get('link')
                    if url:
                        logger.info(f"Uploaded to Imgur: {url}")
                        return url
        except Exception as e:
            logger.debug(f"Imgur failed: {e}")

        # --- SERVICE 2: Catbox.moe ---
        try:
            with open(tmp_path, 'rb') as f:
                r = requests.post('https://catbox.moe/user/api.php', 
                                  data={'reqtype': 'fileupload'}, 
                                  files={'fileToUpload': f}, headers=headers, timeout=10)
                if r.status_code == 200 and r.text.startswith('http'):
                    url = r.text.strip()
                    logger.info(f"Uploaded to Catbox: {url}")
                    return url
        except Exception as e:
            logger.debug(f"Catbox failed: {e}")

        # --- SERVICE 2: BashUpload ---
        try:
            with open(tmp_path, 'rb') as f:
                r = requests.post('https://bashupload.com/', files={'file': f}, headers=headers, verify=False, timeout=10)
                if r.status_code == 200:
                    for line in r.text.split('\n'):
                        if 'https://bashupload.com/' in line:
                            url = line.strip().split(' ')[-1]
                            logger.info(f"Uploaded to BashUpload: {url}")
                            return url
        except Exception as e:
            logger.debug(f"BashUpload failed: {e}")

        # --- SERVICE 3: File.io ---
        try:
            with open(tmp_path, 'rb') as f:
                r = requests.post('https://file.io/?expires=1d', files={'file': f}, headers=headers, timeout=6)
                if r.status_code == 200:
                    url = r.json().get('link')
                    logger.info(f"Uploaded to File.io: {url}")
                    return url
        except Exception as e:
            logger.debug(f"File.io failed: {e}")

    except Exception as e:
        logger.error(f"Image host manager error: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass
    
    return None
