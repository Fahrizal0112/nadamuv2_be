from flask import Flask, jsonify, request
import requests
from youtube_transcript_api import YouTubeTranscriptApi
import re
from urllib.parse import urlparse, parse_qs, unquote
import base64

app = Flask(__name__)

def extract_video_id(youtube_url):
    """
    Extract video ID from YouTube URL
    """
    if not youtube_url:
        return None
    
    # Handle different YouTube URL formats
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([^&\n?#]+)',
        r'youtube\.com/watch\?.*v=([^&\n?#]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, youtube_url)
        if match:
            return match.group(1)
    
    return None

import random
import time

# Tambahkan di bagian atas file
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0'
]

def get_random_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,id;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0'
    }

# Update fungsi get_youtube_transcript
def get_youtube_transcript(video_id, languages=['id', 'en']):
    try:
        # Tambahkan delay random
        time.sleep(random.uniform(0.5, 2.0))
        
        # Monkey patch requests dengan headers
        original_get = requests.get
        def patched_get(url, **kwargs):
            if 'headers' not in kwargs:
                kwargs['headers'] = {}
            kwargs['headers'].update(get_random_headers())
            return original_get(url, **kwargs)
        
        requests.get = patched_get
        
        # Try to get transcript
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try to find transcript in preferred languages
        transcript = None
        for lang in languages:
            try:
                transcript = transcript_list.find_transcript([lang])
                break
            except:
                continue
        
        # If no transcript found in preferred languages, get any available
        if not transcript:
            transcript = transcript_list.find_transcript(['en'])  # fallback to English
        
        # Fetch the actual transcript
        fetched_transcript = transcript.fetch()
        
        # Extract snippets from FetchedTranscript object
        if hasattr(fetched_transcript, 'snippets'):
            # New API version - use snippets attribute
            transcript_data = [{
                'text': snippet.text,
                'start': snippet.start,
                'duration': snippet.duration
            } for snippet in fetched_transcript.snippets]
        else:
            # Fallback for older versions
            transcript_data = fetched_transcript
        
        # Format transcript as a single text
        full_text = ' '.join([item['text'] for item in transcript_data])
        
        return {
            'success': True,
            'transcript': full_text,
            'language': transcript.language,
            'language_code': transcript.language_code,
            'is_generated': transcript.is_generated,
            'raw_data': transcript_data
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'transcript': None
        }

import time
from functools import wraps

# Rate limiting decorator
def rate_limit(calls_per_minute=30):
    min_interval = 60.0 / calls_per_minute
    last_called = [0.0]
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            ret = func(*args, **kwargs)
            last_called[0] = time.time()
            return ret
        return wrapper
    return decorator

@rate_limit(calls_per_minute=20)  # Maksimal 20 calls per menit
def get_youtube_transcript_with_rate_limit(video_id, languages=['id', 'en']):
    return get_youtube_transcript(video_id, languages)

@app.route('/api/chapters/transcript', methods=['GET'])
def get_chapters_with_transcript():
    """
    Fetch chapters from external API and add YouTube transcripts
    """
    try:
        # Fetch data from external API
        response = requests.get('https://nadamu.vpsalfach.my.id/api/chapters/')
        response.raise_for_status()
        
        chapters_data = response.json()
        
        if not chapters_data.get('success'):
            return jsonify({
                'success': False,
                'error': 'Failed to fetch chapters data'
            }), 400
        
        # Process each chapter
        for chapter in chapters_data['data']:
            video_url = chapter.get('videoUrl')
            
            if video_url:
                # Extract video ID
                video_id = extract_video_id(video_url)
                
                if video_id:
                    # Get transcript
                    transcript_result = get_youtube_transcript(video_id)
                    
                    # Update chapter data
                    chapter['transcript'] = transcript_result.get('transcript')
                    chapter['transcriptFetched'] = transcript_result.get('success', False)
                    chapter['transcriptInfo'] = {
                        'language': transcript_result.get('language'),
                        'language_code': transcript_result.get('language_code'),
                        'is_generated': transcript_result.get('is_generated'),
                        'error': transcript_result.get('error')
                    }
                else:
                    chapter['transcript'] = None
                    chapter['transcriptFetched'] = False
                    chapter['transcriptInfo'] = {'error': 'Invalid YouTube URL'}
            else:
                chapter['transcript'] = None
                chapter['transcriptFetched'] = False
                chapter['transcriptInfo'] = {'error': 'No video URL provided'}
        
        return jsonify(chapters_data)
        
    except requests.RequestException as e:
        return jsonify({
            'success': False,
            'error': f'Failed to fetch chapters: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500

@app.route('/api/transcript/<video_id>', methods=['GET'])
def get_single_transcript(video_id):
    """
    Get transcript for a single YouTube video
    """
    languages = request.args.getlist('lang') or ['id', 'en']
    
    result = get_youtube_transcript(video_id, languages)
    
    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 400

@app.route('/api/transcript/url', methods=['POST'])
def get_transcript_from_url():
    """
    Get transcript from YouTube URL
    """
    data = request.get_json()
    
    if not data or 'url' not in data:
        return jsonify({
            'success': False,
            'error': 'YouTube URL is required'
        }), 400
    
    video_id = extract_video_id(data['url'])
    
    if not video_id:
        return jsonify({
            'success': False,
            'error': 'Invalid YouTube URL'
        }), 400
    
    languages = data.get('languages', ['id', 'en'])
    result = get_youtube_transcript(video_id, languages)
    
    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 400

@app.route('/api/transcript/url/<path:encoded_url>', methods=['GET'])
def get_transcript_from_url_param(encoded_url):
    try:
        # Decode base64 URL
        try:
            decoded_url = base64.b64decode(encoded_url).decode('utf-8')
        except:
            # Jika bukan base64, coba decode URL biasa
            decoded_url = unquote(encoded_url)
        
        # Extract video ID
        video_id = extract_video_id(decoded_url)
        
        if not video_id:
            return jsonify({
                'success': False,
                'error': 'Invalid YouTube URL',
                'provided_url': decoded_url
            }), 400
        
        # Get languages from query parameters
        languages = request.args.getlist('lang') or ['id', 'en']
        
        # Get transcript
        result = get_youtube_transcript(video_id, languages)
        
        # Add original URL info to response
        result['original_url'] = decoded_url
        result['video_id'] = video_id
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error processing URL: {str(e)}',
            'provided_encoded_url': encoded_url
        }), 500

@app.route('/api/transcript/direct', methods=['GET'])
def get_transcript_direct():
    """
    Get transcript from YouTube URL passed as query parameter
    Lebih mudah digunakan tanpa perlu encoding
    
    Contoh penggunaan:
    GET /api/transcript/direct?url=https://youtu.be/f9cwrjDGOHo?si=vmEWMvEMsMC6yWlB
    """
    youtube_url = request.args.get('url')
    
    if not youtube_url:
        return jsonify({
            'success': False,
            'error': 'YouTube URL parameter is required',
            'usage': 'GET /api/transcript/direct?url=YOUTUBE_URL'
        }), 400
    
    # Extract video ID
    video_id = extract_video_id(youtube_url)
    
    if not video_id:
        return jsonify({
            'success': False,
            'error': 'Invalid YouTube URL',
            'provided_url': youtube_url
        }), 400
    
    # Get languages from query parameters
    languages = request.args.getlist('lang') or ['id', 'en']
    
    # Get transcript
    result = get_youtube_transcript(video_id, languages)
    
    # Add original URL info to response
    result['original_url'] = youtube_url
    result['video_id'] = video_id
    
    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 400

# Helper endpoint untuk encoding URL
@app.route('/api/encode-url', methods=['POST'])
def encode_youtube_url():
    """
    Helper endpoint untuk encode YouTube URL ke base64
    """
    data = request.get_json()
    
    if not data or 'url' not in data:
        return jsonify({
            'success': False,
            'error': 'URL is required'
        }), 400
    
    url = data['url']
    encoded_url = base64.b64encode(url.encode('utf-8')).decode('utf-8')
    
    return jsonify({
        'success': True,
        'original_url': url,
        'encoded_url': encoded_url,
        'usage_example': f'/api/transcript/url/{encoded_url}'
    })

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'message': 'YouTube Transcript API is running'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=4000)


import json
import os
from datetime import datetime, timedelta

# Simple file-based caching
CACHE_DIR = 'transcript_cache'
CACHE_DURATION = 24 * 60 * 60  # 24 jam

def ensure_cache_dir():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def get_cache_path(video_id):
    return os.path.join(CACHE_DIR, f"{video_id}.json")

def get_cached_transcript(video_id):
    cache_path = get_cache_path(video_id)
    if os.path.exists(cache_path):
        # Cek apakah cache masih valid
        cache_time = os.path.getmtime(cache_path)
        if time.time() - cache_time < CACHE_DURATION:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    return None

def save_transcript_cache(video_id, transcript):
    ensure_cache_dir()
    cache_path = get_cache_path(video_id)
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(transcript, f, ensure_ascii=False, indent=2)

def get_youtube_transcript_cached(video_id, languages=['id', 'en']):
    # Cek cache dulu
    cached = get_cached_transcript(video_id)
    if cached:
        return cached
    
    # Ambil dari YouTube jika tidak ada cache
    transcript = get_youtube_transcript_with_rate_limit(video_id, languages)
    
    # Simpan ke cache
    save_transcript_cache(video_id, transcript)
    
    return transcript


## 4. **Multiple Fallback Strategies**
def get_youtube_transcript_with_fallback(video_id, languages=['id', 'en']):
    strategies = [
        # Strategy 1: Normal dengan headers
        lambda: get_youtube_transcript_cached(video_id, languages),
        
        # Strategy 2: Dengan delay lebih lama
        lambda: (time.sleep(5), get_youtube_transcript(video_id, languages))[1],
        
        # Strategy 3: Hanya bahasa Inggris
        lambda: get_youtube_transcript(video_id, ['en']),
        
        # Strategy 4: Auto-generated transcript
        lambda: YouTubeTranscriptApi.get_transcript(video_id, languages=['en'], 
                                                   preserve_formatting=True)
    ]
    
    for i, strategy in enumerate(strategies):
        try:
            print(f"Trying strategy {i+1}...")
            result = strategy()
            print(f"Strategy {i+1} succeeded")
            return result
        except Exception as e:
            print(f"Strategy {i+1} failed: {str(e)}")
            if i < len(strategies) - 1:
                # Exponential backoff
                wait_time = (2 ** i) * random.uniform(1, 3)
                print(f"Waiting {wait_time:.1f}s before next strategy...")
                time.sleep(wait_time)
            continue
    
    raise Exception("All fallback strategies failed")

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Global session dengan retry strategy
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

def setup_session_headers():
    session.headers.update(get_random_headers())

# Update monkey patch untuk menggunakan session
def patch_requests_with_session():
    original_get = requests.get
    original_post = requests.post
    
    def patched_get(url, **kwargs):
        setup_session_headers()
        return session.get(url, **kwargs)
    
    def patched_post(url, **kwargs):
        setup_session_headers()
        return session.post(url, **kwargs)
    
    requests.get = patched_get
    requests.post = patched_post
    
    return original_get, original_post