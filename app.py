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

def get_youtube_transcript(video_id, languages=['id', 'en']):
    """
    Get transcript from YouTube video
    """
    try:
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