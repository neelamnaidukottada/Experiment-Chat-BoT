# Project 6: Google Gemini 2.0 Image Generation - API Key Setup

## Issue Encountered
The Google Gemini API key currently in the system has been reported as **leaked/compromised** and is blocked from the Google AI API. We need to generate a fresh API key.

## Steps to Generate New API Key

### 1. Get a New API Key
- Go to: https://aistudio.google.com/app/apikey
- Sign in with your Google account
- Click **"Create API Key"** button
- Choose your project (or create a new one)
- Copy the new API key (it will be a long string starting with `AIza...`)

### 2. Update .env File
Edit `backend/.env` file and add/update:
```
GOOGLE_GEMINI_API_KEY=<YOUR_NEW_API_KEY_HERE>
```

Example:
```
GOOGLE_GEMINI_API_KEY=AIzaSyXxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. Enable Image Generation API
In Google Cloud Console:
1. Go to: https://console.cloud.google.com
2. Make sure your project is selected (top-left dropdown)
3. Enable "Google AI API" if not already enabled
4. The Imagen API should be available for use

### 4. Restart Backend
```bash
cd backend
# Kill existing backend process
# Then restart:
python run.py
```

Or if using Uvicorn directly:
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 5. Test Image Generation
1. Open http://localhost:5174 in browser
2. Log in to chat
3. Click the menu button (+) in input area
4. Click "🎨 Create image"
5. Enter a prompt like: "a beautiful sunset over mountains"
6. Wait for image to generate and appear in chat

## Available Image Generation Models

The system is now configured to use: `models/imagen-3.0-generate-001`

This is Google's dedicated image generation model with good quality and speed.

## Troubleshooting

### If you get "404 NOT_FOUND" error:
- Verify API key is correct (no extra spaces or characters)
- Check that the model name is correct in `settings.py`
- Ensure the Image Generation API is enabled in Google Cloud Console

### If you get "403 PERMISSION_DENIED" error:
- Your API key might still be compromised
- Generate a new one and try again

### If image generation is slow:
- First image generation may take 10-15 seconds
- Subsequent requests are typically faster
- Check browser console for progress

## Current Status
- ✅ Backend infrastructure ready
- ✅ Frontend UI buttons implemented
- ✅ Image service code deployed
- ⏳ Awaiting new API key configuration
- ⏳ Ready for testing once API key is updated

## Quick Reference

| Component | Status | Notes |
|-----------|--------|-------|
| Backend API | ✅ Running on 8000 | FastAPI + Uvicorn |
| Frontend UI | ✅ Running on 5174 | React + Vite |
| Image Service | ✅ Deployed | Uses google-genai SDK |
| Database | ✅ Connected | PostgreSQL via Supabase |
| Image Model | ✅ Configured | models/imagen-3.0-generate-001 |
| API Key | ❌ Compromised | Needs replacement |

## Next Steps
1. ✏️ Generate new API key from https://aistudio.google.com/app/apikey
2. 📝 Update `backend/.env` with new key
3. 🔄 Restart the backend
4. 🧪 Test image generation in the chat interface
