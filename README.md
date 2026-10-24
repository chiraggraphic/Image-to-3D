# Image to 3D

Upload an image, get a detailed textured 3D model (GLB, FBX, OBJ, USDZ, STL).
Uses Meshy's official API, so you get the same models as meshy.ai.

## Run
```bash
pip install -r requirements.txt
cp .env.example .env        # then paste your Meshy API key into .env
uvicorn main:app --reload
```
Open http://127.0.0.1:8000

## How it works
1. Browser uploads the image to `/api/convert`.
2. The server sends it to Meshy (`POST /openapi/v1/image-to-3d`) and returns the task id.
3. The browser polls `/api/task/{id}` every 3 seconds.
4. When the status is SUCCEEDED, the GLB loads in the viewer and every format gets a download button.
   Files stream through `/api/download`, which only accepts meshy.ai asset URLs.

## Notes
- Meshy bills API credits per task. Check the pricing page for your plan.
- If a format (for example STL) is missing, set `TARGET_FORMATS` in `.env`.
- Never put the API key in the HTML or JavaScript. It stays in `.env`.
